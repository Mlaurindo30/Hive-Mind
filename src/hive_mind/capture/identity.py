"""The one place capture decides what project a session belongs to (D004-R2).

Before this module, identity was decided by whoever remembered to ask. The
realtime watcher called `attach_project_identity`; the tailer job did not, and
wrote whatever the parser had guessed straight into the field Claude Mem
groups by. Both were declared in `runtime.yaml`, both wrote to the same store,
and the difference is visible in real data: prompt text became a project name,
and this repository's worktree became a project separate from its own root.

The fix is not to make the tailer remember too. Two places that must remember
the same thing is how this happened. Identity is decided here, `ingest` calls
it unconditionally, and entrypoints supply evidence rather than answers.
"""
from __future__ import annotations

from typing import Any, Optional

from hive_mind.capture.models import CaptureIdentity, IdentityRefused, IdentityStatus
from hive_mind.projects.identity import (
    ProjectIdentity,
    ProjectIdentityError,
    ProjectIdentityResolver,
)

# Envelope fields that must be present and non-empty for an envelope supplied
# by an entrypoint to be trusted at all.
REQUIRED_ENVELOPE_FIELDS = ("project_id", "project_name", "resolution_method")

_UNCLASSIFIED_PREFIX = "unclassified/"


def _clean(value: Any) -> Optional[str]:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: Any) -> str:
    text = (_clean(value) or "").casefold()
    slug = "".join(
        c if c.isascii() and (c.isalnum() or c in "._-") else "-" for c in text
    )
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-._")


def _references(value: Any) -> tuple[str, ...]:
    values = (value,) if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    out, seen = [], set()
    for item in values:
        text = _clean(item)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return tuple(out)


def unclassified_identity(provider: str, surface: str, workspace: Optional[str],
                          referenced: Any = (),
                          method: str = "insufficient_evidence") -> ProjectIdentity:
    """The deterministic answer when identity cannot be established.

    Deterministic matters: the same provider with the same absent evidence
    must always yield the same id, or `unclassified` would itself become a
    source of fragmentation. It borrows nothing from prompt text or from a
    directory basename.

    `method` keeps two different situations distinguishable in the audit
    trail, because they call for different follow-up:

    - `insufficient_evidence` — there was nothing to go on. Expected, common,
      and nobody's fault.
    - `invalid_evidence_fallback` — evidence was supplied and the resolver
      rejected it. Something upstream is misconfigured and worth finding.

    Both deliver; collapsing them into one label would hide the second.
    """
    provider_key = _slug(provider) or "unknown"
    return ProjectIdentity(
        project_id=f"{_UNCLASSIFIED_PREFIX}{provider_key}",
        project_name=f"Unclassified ({provider_key})",
        workspace_root=workspace,
        repository_root=None,
        repository_remote=None,
        git_common_dir=None,
        worktree_name=None,
        branch=None,
        provider=provider_key,
        surface=_slug(surface) or "unknown",
        resolution_method=method,
        resolution_confidence=0.0,
        referenced_projects=_references(referenced),
    )


def _known_legacy_project(resolver: ProjectIdentityResolver,
                          value: Optional[str]) -> Optional[str]:
    """A free label is evidence only if the alias registry recognises it.

    This is the narrow door the raw label is allowed through: a label the
    project has explicitly registered as an alias is a curated mapping, not a
    parser's guess. Anything else is discarded as authority.
    """
    if value is None:
        return None
    registry = getattr(resolver, "registry", None)
    by_alias = getattr(registry, "by_alias", None)
    return value if callable(by_alias) and by_alias(value) is not None else None


def validate_envelope(envelope: Any, *, provider: str) -> dict[str, Any]:
    """Check an envelope an entrypoint already attached. Never trust it blindly.

    A hook computes an envelope of its own, and a session can arrive with one
    already in place. Accepting it unread would reintroduce the problem from a
    different direction: a second implementation deciding identity.
    """
    if not isinstance(envelope, dict):
        raise IdentityRefused("envelope is not an object", provider=provider,
                              detail=type(envelope).__name__)
    missing = [f for f in REQUIRED_ENVELOPE_FIELDS if not _clean(envelope.get(f))]
    if missing:
        raise IdentityRefused("envelope is missing required fields",
                              provider=provider, detail=", ".join(missing))

    project_id = _clean(envelope["project_id"]) or ""
    if project_id != project_id.strip() or "\n" in project_id:
        raise IdentityRefused("project_id is malformed", provider=provider,
                              detail=repr(project_id))
    return dict(envelope)


def _envelope_contradicts_evidence(envelope: dict[str, Any],
                                   resolved: ProjectIdentity) -> Optional[str]:
    """Whether a supplied envelope disagrees with what the evidence resolves to.

    Only a disagreement about *identity* counts. Branch and worktree move
    between the moment a hook fires and the moment a tailer reads the file, so
    a difference there is expected and is not a contradiction.
    """
    claimed = _clean(envelope.get("project_id"))
    if not claimed or claimed == resolved.project_id:
        return None
    # An envelope that gave up is allowed to be superseded by a better answer.
    if claimed.startswith(_UNCLASSIFIED_PREFIX):
        return None
    # And a resolver that gave up must not overwrite a specific claim.
    if resolved.project_id.startswith(_UNCLASSIFIED_PREFIX):
        return None
    return f"envelope claims {claimed}, evidence resolves to {resolved.project_id}"


def resolve_identity(provider: str, session: dict, *,
                     resolver: ProjectIdentityResolver,
                     default_surface: Optional[str] = None) -> CaptureIdentity:
    """Decide the identity of one session. The only function that may.

    Raises `IdentityRefused` before anything is written when the session
    cannot yield a usable identity — never after a partial write.
    """
    session = session or {}
    provider_name = _clean(provider) or ""
    if not provider_name:
        raise IdentityRefused("no provider given")

    cwd = _clean(session.get("cwd"))
    surface = (_clean(session.get("surface")) or _clean(session.get("source"))
               or _clean(default_surface) or "unknown")
    workspace = (_clean(session.get("official_workspace"))
                 or _clean(session.get("workspace_root"))
                 or _clean(session.get("workspace"))
                 or _clean(session.get("git_repo_root")))
    raw_label = _clean(session.get("project"))

    supplied = session.get("project_identity")
    validated = validate_envelope(supplied, provider=provider_name) if supplied else None

    try:
        resolved = resolver.resolve(
            provider=provider_name,
            surface=surface,
            cwd=cwd,
            explicit_project_id=_clean(session.get("project_id")),
            explicit_project_name=_clean(session.get("project_name")),
            # The parser's label is not authority. It is offered only when the
            # alias registry already recognises it as a curated mapping.
            explicit_project=_known_legacy_project(resolver, raw_label),
            official_workspace=workspace,
            referenced_projects=session.get("referenced_projects") or (),
        )
    except ProjectIdentityError:
        # Evidence was offered and rejected — not the same as no evidence.
        resolved = unclassified_identity(provider_name, surface, workspace or cwd,
                                         session.get("referenced_projects"),
                                         method="invalid_evidence_fallback")

    if validated is not None:
        contradiction = _envelope_contradicts_evidence(validated, resolved)
        if contradiction:
            raise IdentityRefused("envelope contradicts its own evidence",
                                  provider=provider_name, detail=contradiction)

    envelope = resolved.to_dict()
    status = (IdentityStatus.UNCLASSIFIED
              if resolved.project_id.startswith(_UNCLASSIFIED_PREFIX)
              else IdentityStatus.CLASSIFIED)

    return CaptureIdentity(
        project_id=resolved.project_id,
        project_name=resolved.project_name,
        status=status,
        provider=provider_name,
        surface=surface,
        resolution_method=resolved.resolution_method or "",
        resolution_confidence=float(resolved.resolution_confidence or 0.0),
        workspace_root=resolved.workspace_root,
        repository_root=resolved.repository_root,
        repository_remote=resolved.repository_remote,
        git_common_dir=resolved.git_common_dir,
        worktree_name=resolved.worktree_name,
        branch=resolved.branch,
        referenced_projects=tuple(resolved.referenced_projects or ()),
        raw_label=raw_label,
        envelope=envelope,
    )


def apply_identity(session: dict, identity: CaptureIdentity) -> dict:
    """Return the session with canonical identity, and no free label left standing.

    `project` and `project_name` become the canonical name. The parser's label
    survives only inside `metadata.capture.raw_project_label`, where nothing
    groups, filters or builds a path from it.
    """
    normalized = dict(session or {})
    normalized.update(identity.envelope)
    normalized["project_identity"] = dict(identity.envelope)
    normalized["project"] = identity.project_name
    normalized["project_name"] = identity.project_name
    normalized["project_id"] = identity.project_id
    normalized["identity_status"] = identity.status.value

    # The legacy hook already signals degradation with this key, and
    # `capture-hook.py` reads it. Emitting the same shape here keeps one
    # vocabulary for "this identity is a fallback" across every path,
    # instead of a second one that consumers would have to learn.
    if identity.status is IdentityStatus.UNCLASSIFIED:
        normalized["project_identity_diagnostics"] = [{
            "component": "project_identity",
            "status": "degraded",
            "reason": ("invalid_evidence"
                       if identity.resolution_method == "invalid_evidence_fallback"
                       else "insufficient_evidence"),
        }]
    else:
        normalized.pop("project_identity_diagnostics", None)

    metadata = normalized.get("metadata")
    merged = dict(metadata) if isinstance(metadata, dict) else {}
    merged.update(identity.to_metadata())
    normalized["metadata"] = merged
    return normalized
