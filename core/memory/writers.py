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
from datetime import datetime
from typing import Any, Callable, List, Optional


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
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, filepath)
        return True
    except OSError:
        return False


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
) -> Optional[str]:
    """
    Salva uma decisão no vault: work/active/YYYY-MM-DD-titulo.md

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
    slug = sanitize_slug(title)
    filename = f"{today}-{slug}.md"
    filepath = os.path.join(decisions_dir, filename)

    note = (
        f"---\n"
        f"tags: [decision]\n"
        f"status: active\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"source: hermes-session\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content}\n"
    )

    if not validate_frontmatter_yaml(note) and log_fn:
        log_fn("error", "frontmatter_invalid", file=filepath)

    if atomic_write(filepath, note):
        if log_fn:
            log_fn("info", "decision_saved", title=title[:60], file=filepath)
        if umc_save_fn:
            umc_save_fn(title, content, "decision")
        return filepath

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
) -> Optional[str]:
    """
    Salva um aprendizado em brain/Patterns.md com deduplicação.
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
        with open(patterns_file, "r") as f:
            existing = f.read()
        if re.search(rf"^## {re.escape(title)} \(", existing, re.MULTILINE):
            if log_fn:
                log_fn("info", "learning_duplicate_skipped", title=title[:60])
            return None
    except FileNotFoundError:
        pass

    entry = f"\n\n---\n\n## {title} ({today})\n\n{content}\n"

    try:
        existing = ""
        try:
            with open(patterns_file, "r") as f:
                existing = f.read()
        except FileNotFoundError:
            pass

        if atomic_write(patterns_file, existing + entry):
            if log_fn:
                log_fn("info", "learning_saved", title=title[:60])
            if umc_save_fn:
                umc_save_fn(title, content, "learning")
            return patterns_file

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
    Atualiza brain/Current State.md com as decisões e aprendizados da sessão.
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
        with open(memory_file, "r") as f:
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
