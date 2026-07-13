"""
Write helpers: save_decision, save_learning, update_current_state.

Puro — recebe todos os parâmetros como argumentos (incluindo paths de arquivo),
sem acessar globals do módulo pai. Isso garante que monkeypatch.setattr em
DECISIONS_DIR, PATTERNS_FILE, MEMORY_FILE funcione corretamente quando o
chamador (sinapse-memory.py) passa seus próprios valores atuais.
"""

import os
import re
import tempfile
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Callable, List, Optional


# Validade temporal por nota (federated-memory): toda nota promovida carrega
# a data da última revisão humana e o prazo da próxima; o audit sinaliza
# vencidas e o RetrievalRouter rebaixa o score após o prazo.
REVIEW_TTL_DAYS = 90


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


def sanitize_slug(title: str, max_len: int = 60) -> str:
    """Sanitiza título para slug de arquivo seguro."""
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ASCII", "ignore").decode("ASCII")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    return text or "decision"


def atomic_write(filepath: str, content: str) -> bool:
    """Escreve arquivo atomicamente via temp + rename."""
    dirname = os.path.dirname(filepath)
    os.makedirs(dirname, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dirname, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp_path, filepath)
        return True
    except OSError:
        return False


def intake_fallback_dir(target_path: str) -> Optional[str]:
    """Área de intake do vault para quando a escrita direta é negada.

    Com o enforcement de vault ativo (setup-vault-enforcement.sh), agentes só
    têm escrita em cerebro/90-intake/ — o Dream Cycle promove de lá para o
    destino final. HIVE_INTAKE_DIR tem precedência; sem ela, deriva
    <vault>/90-intake do próprio path de destino.
    """
    explicit = os.environ.get("HIVE_INTAKE_DIR", "").strip()
    if explicit:
        return explicit
    parts = os.path.normpath(target_path).split(os.sep)
    if "cerebro" not in parts:
        return None
    vault_root = os.sep.join(parts[: parts.index("cerebro") + 1])
    return os.path.join(vault_root, "90-intake")


def _write_with_intake_fallback(
    filepath: str,
    note: str,
    *,
    log_fn: Optional[Callable],
    event: str,
) -> Optional[str]:
    """atomic_write com fallback para a área de intake em falha de escrita."""
    if atomic_write(filepath, note):
        return filepath
    intake_dir = intake_fallback_dir(filepath)
    if not intake_dir:
        return None
    intake_path = os.path.join(intake_dir, os.path.basename(filepath))
    intake_note = note.replace(
        "---\n", f"---\npromote_to: \"{filepath}\"\n", 1
    ) if note.startswith("---\n") else note
    if atomic_write(intake_path, intake_note):
        if log_fn:
            log_fn("info", event, file=intake_path, promote_to=filepath)
        return intake_path
    return None


def validate_frontmatter_yaml(content: str) -> bool:
    """Verifica se o frontmatter YAML é válido."""
    if not content.startswith("---"):
        return False
    try:
        parts = content.split("---", 2)
        if len(parts) < 3:
            return False
        yaml_content = parts[1].strip()
        return all(k in yaml_content for k in ("tags:", "status:", "created:"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def save_decision(
    title: str,
    content: str,
    decisions_dir: str,
    dry_run: bool = False,
    log_fn: Optional[Callable] = None,
    umc_save_fn: Optional[Callable] = None,
    cloud_enabled: bool = False,
    api_server_mode: bool = False,
    cloud_request_fn: Optional[Callable] = None,
    evidence: Optional[str] = None,
) -> Optional[str]:
    """
    Salva uma decisão no diretório anatômico recebido pelo chamador
    (normalmente cortex/frontal/trabalho/ativo/).

    Args:
        title: título da decisão.
        content: conteúdo da decisão.
        decisions_dir: caminho para o diretório de decisões.
        dry_run: se True, não cria arquivos.
        log_fn: callable(level, event, **kwargs).
        umc_save_fn: callable(title, content, obs_type) para espelhar no UMC.
        cloud_enabled: se True, usa cloud se não for API server mode.
        api_server_mode: se True, não redireciona para cloud.
        cloud_request_fn: callable(endpoint, method, data) para cloud.
        evidence: artefato que valida a decisão (comando, teste, arquivo).
            Com evidence a nota nasce confidence=verified; sem, hypothesis.
    """
    if cloud_enabled and not api_server_mode and cloud_request_fn is not None:
        if log_fn:
            log_fn("info", "save_decision_cloud", title=title[:60])
        res = cloud_request_fn("decision", method="POST", data={"title": title, "content": content})
        if res and res.get("saved"):
            return res.get("path")
        return None

    if dry_run:
        if log_fn:
            log_fn("info", "dry_run", action="save_decision", title=title[:60])
        return "/dev/null/dry-run"

    today = datetime.now().strftime("%Y-%m-%d")
    next_review = (datetime.now() + timedelta(days=REVIEW_TTL_DAYS)).strftime("%Y-%m-%d")
    slug = sanitize_slug(title)
    filename = f"{today}-{slug}.md"
    filepath = os.path.join(decisions_dir, filename)

    # Edge case (R2, post-audit stabilization spec): empty content is rejected
    # BEFORE any file is created. The caller sees {error: "content_empty"}.
    if not content or not content.strip():
        if log_fn:
            log_fn("error", "content_empty", title=title[:60])
        return None

    confidence = "verified" if evidence else "hypothesis"
    evidence_line = f"evidence: \"{evidence}\"\n" if evidence else ""
    note = (
        f"---\n"
        f"tags: [decision]\n"
        f"status: active\n"
        f"confidence: {confidence}\n"
        f"{evidence_line}"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"review_date: {today}\n"
        f"next_review: {next_review}\n"
        f"source: hermes-session\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content}\n"
    )

    # Edge case (R2, post-audit stabilization spec): invalid frontmatter is
    # rejected BEFORE the file is written. The caller sees
    # {error: "frontmatter_invalid"}.
    if not validate_frontmatter_yaml(note):
        if log_fn:
            log_fn("error", "frontmatter_invalid", file=filepath)
        return None

    saved_path = _write_with_intake_fallback(
        filepath, note, log_fn=log_fn, event="decision_saved_intake"
    )
    if saved_path:
        if log_fn:
            log_fn("info", "decision_saved", title=title[:60], file=saved_path)
        if umc_save_fn:
            umc_save_fn(title, content, "decision")
        return saved_path

    if log_fn:
        log_fn("error", "save_decision_failed", title=title[:60], file=filepath)
    return None


def save_learning(
    title: str,
    content: str,
    patterns_file: str,
    dry_run: bool = False,
    log_fn: Optional[Callable] = None,
    umc_save_fn: Optional[Callable] = None,
    cloud_enabled: bool = False,
    api_server_mode: bool = False,
    cloud_request_fn: Optional[Callable] = None,
    evidence: Optional[str] = None,
) -> Optional[str]:
    """
    Salva um aprendizado em cerebelo/padroes/Patterns.md com deduplicação.

    Com `evidence` (comando, teste, arquivo) a entrada nasce
    confidence=verified; sem, hypothesis — aguardando validação.
    """
    if cloud_enabled and not api_server_mode and cloud_request_fn is not None:
        if log_fn:
            log_fn("info", "save_learning_cloud", title=title[:60])
        res = cloud_request_fn("learning", method="POST", data={"title": title, "content": content})
        if res and res.get("saved"):
            return res.get("path")
        return None

    if dry_run:
        if log_fn:
            log_fn("info", "dry_run", action="save_learning", title=title[:60])
        return "/dev/null/dry-run"

    today = datetime.now().strftime("%Y-%m-%d")

    # Verifica duplicação — match de heading exato
    try:
        with open(patterns_file, "r", encoding="utf-8") as f:
            existing = f.read()
        if re.search(rf"^## {re.escape(title)} \(", existing, re.MULTILINE):
            if log_fn:
                log_fn("info", "learning_duplicate_skipped", title=title[:60])
            return None
    except FileNotFoundError:
        pass

    next_review = (datetime.now() + timedelta(days=REVIEW_TTL_DAYS)).strftime("%Y-%m-%d")
    confidence = "verified" if evidence else "hypothesis"
    governance_line = f"> confidence: {confidence} · next_review: {next_review}"
    if evidence:
        governance_line += f" · evidence: {evidence}"
    entry = f"\n\n---\n\n## {title} ({today})\n\n{governance_line}\n\n{content}\n"

    try:
        existing = ""
        try:
            with open(patterns_file, "r", encoding="utf-8") as f:
                existing = f.read()
        except FileNotFoundError:
            pass

        if atomic_write(patterns_file, existing + entry):
            if log_fn:
                log_fn("info", "learning_saved", title=title[:60])
            if umc_save_fn:
                umc_save_fn(title, content, "learning")
            return patterns_file

        # Escrita direta negada (enforcement de vault): deposita a entrada
        # como nota avulsa na área de intake para o Dream Cycle promover.
        intake_dir = intake_fallback_dir(patterns_file)
        if intake_dir:
            intake_path = os.path.join(
                intake_dir, f"{today}-learning-{sanitize_slug(title)}.md"
            )
            intake_note = (
                f"---\n"
                f"tags: [learning]\n"
                f"status: intake\n"
                f"confidence: {confidence}\n"
                f"promote_to: \"{patterns_file}\"\n"
                f"created: {today}\n"
                f"---\n{entry}"
            )
            if atomic_write(intake_path, intake_note):
                if log_fn:
                    log_fn("info", "learning_saved_intake", title=title[:60], file=intake_path)
                if umc_save_fn:
                    umc_save_fn(title, content, "learning")
                return intake_path

        if log_fn:
            log_fn("error", "save_learning_failed", title=title[:60], error="atomic_write returned False")
        return None
    except OSError as e:
        if log_fn:
            log_fn("error", "save_learning_failed", title=title[:60], error=str(e))
        return None


def update_current_state(
    decisions: List[str],
    learnings: List[str],
    summary: str,
    memory_file: str,
    dry_run: bool = False,
    log_fn: Optional[Callable] = None,
    cloud_enabled: bool = False,
    api_server_mode: bool = False,
    cloud_request_fn: Optional[Callable] = None,
) -> None:
    """
    Atualiza cortex/frontal/brain/Current State.md com as decisões e aprendizados da sessão.
    """
    if cloud_enabled and not api_server_mode and cloud_request_fn is not None:
        if log_fn:
            log_fn("info", "update_current_state_cloud")
        cloud_request_fn(
            "session-end",
            method="POST",
            data={"summary": summary, "decisions": decisions, "learnings": learnings},
        )
        return

    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    os.makedirs(os.path.dirname(memory_file), exist_ok=True)

    existing = ""
    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            existing = f.read()
    except FileNotFoundError:
        pass

    decision_lines = "".join(
        f"- Decisão: [[{os.path.basename(d).replace('.md', '')}]]\n"
        for d in decisions[-5:]
    )
    learning_lines = "".join(
        f"- Aprendizado: [[{os.path.basename(l).replace('.md', '')}]]\n"
        for l in learnings[-5:]
    )

    session_block = (
        f"\n\n## Session: {today}\n\n"
        f"### Decisions\n"
        f"{decision_lines or '- Nenhuma decisão registrada'}"
        f"### Learnings\n"
        f"{learning_lines or '- Nenhum aprendizado registrado'}"
        f"### Summary\n"
        f"{summary[:500]}\n"
    )

    updated = re.sub(
        r"^## Last Update:.*$",
        f"## Last Update: {today}",
        existing,
        flags=re.MULTILINE,
    )
    if "## Last Update:" not in updated:
        updated = f"## Last Update: {today}\n\n{updated}"

    updated += session_block

    if not atomic_write(memory_file, updated) and log_fn:
        log_fn("error", "update_current_state_failed", file=memory_file)
