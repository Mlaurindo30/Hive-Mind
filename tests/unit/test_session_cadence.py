"""Testes de regressão da cadência de sessão (Fase 1 — Memória Viva §11).

Cobre:
- `session_placeholder` cria o arquivo a partir do template com placeholders
  substituídos. Idempotente: 2ª chamada não sobrescreve.
- `session_update` faz append idempotente na seção ## Ações. Throttle 1s/sessão
  via mtime. Ignora sessão já consolidada.
- `daily_writer` agrega N sessões em 1 daily (LLM pulado via --no-llm).
- Path real: `cerebro/cerebelo/sessoes/...` (NÃO `/cortex/cerebelo/` do doc).
- Papéis LLM novos: `session_summarizer` e `daily_writer` estão em CANONICAL_ROLES.

Nenhum teste chama LLM nem depende do hive_mind.db real.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SCRIPTS = {
    "placeholder": SCRIPTS_DIR / "session_placeholder.py",
    "update": SCRIPTS_DIR / "session_update.py",
    "consolidator": SCRIPTS_DIR / "session_consolidator.py",
    "daily": SCRIPTS_DIR / "daily_writer.py",
}


def _venv_python() -> str:
    venv = PROJECT_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _run_script(name: str, *args: str, stdin: str = "", env: dict | None = None) -> subprocess.CompletedProcess:
    """Roda um dos scripts da cadência como subprocess isolado.

    Para testes, aponta SINAPSE_HOME para tmp_path e redireciona os roots
    de cerebelo via env overrides (SESSIONS_ROOT_OVERRIDE, DAILY_ROOT_OVERRIDE,
    SESSION_TEMPLATE_PATH, DAILY_TEMPLATE_PATH).
    """
    full_env = os.environ.copy()
    full_env["PYTHONPATH"] = str(PROJECT_ROOT)
    if env:
        full_env.update(env)
    # O `env` já deve conter SINAPSE_HOME apontando para tmp_path
    sinapse_home = full_env.get("SINAPSE_HOME", str(PROJECT_ROOT))
    full_env.setdefault("SESSIONS_ROOT_OVERRIDE", str(Path(sinapse_home) / "cerebro" / "cerebelo" / "sessoes"))
    full_env.setdefault("DAILY_ROOT_OVERRIDE", str(Path(sinapse_home) / "cerebro" / "cerebelo" / "diario"))
    full_env.setdefault("SESSION_TEMPLATE_PATH", str(PROJECT_ROOT / "cerebro" / "tronco" / "modelos" / "session-log.md"))
    full_env.setdefault("DAILY_TEMPLATE_PATH", str(PROJECT_ROOT / "cerebro" / "tronco" / "modelos" / "daily-log.md"))
    return subprocess.run(
        [_venv_python(), str(SCRIPTS[name]), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


class TestSessionPlaceholder:
    """Cria arquivo de sessão a partir do template."""

    def test_placeholder_creates_session_file(self, tmp_path):
        result = _run_script(
            "placeholder",
            env={
                "SINAPSE_HOME": str(tmp_path),
                "CLAUDE_SESSION_ID": "test-session-1",
                "DRY_RUN": "0",
            },
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Verifica que o arquivo foi criado no SESSIONS_ROOT_OVERRIDE
        sessions_root = Path(
            str(tmp_path)  # SINAPSE_HOME
        ) / "cerebro" / "cerebelo" / "sessoes"
        created = list(sessions_root.rglob("*-test-session-1.md"))
        assert len(created) == 1, f"Esperava 1 arquivo, encontrei {len(created)} em {sessions_root}: {[str(p) for p in sessions_root.rglob('*.md')]}"
        content = created[0].read_text(encoding="utf-8")
        assert "type: session-log" in content
        assert "test-session-1" in content
        assert "## Ações" in content
        assert "## Resumo" in content
        assert "{{" not in content, f"Placeholders não substituídos em: {content[:300]}"

    def test_placeholder_is_idempotent(self, tmp_path):
        env = {
            "SINAPSE_HOME": str(tmp_path),
            "CLAUDE_SESSION_ID": "test-idempotent",
            "DRY_RUN": "0",
        }
        _run_script("placeholder", env=env)
        result = _run_script("placeholder", env=env, stdin="(junk)\n")
        assert "já existe" in result.stderr, f"Esperava idempotência no stderr, veio: {result.stderr}"

    def test_placeholder_dry_run_does_not_write(self, tmp_path):
        result = _run_script(
            "placeholder",
            env={
                "SINAPSE_HOME": str(tmp_path),
                "CLAUDE_SESSION_ID": "test-dry",
                "DRY_RUN": "1",
            },
        )
        sessions_root = Path(str(tmp_path)) / "cerebro" / "cerebelo" / "sessoes"
        assert not sessions_root.exists(), f"DRY_RUN não deveria criar nada; existe: {sessions_root}"
        assert "DRY_RUN" in result.stderr


class TestSessionUpdate:
    """Faz append incremental no session log ativo."""

    def test_update_appends_to_active_session(self, tmp_path):
        env = {"SINAPSE_HOME": str(tmp_path), "CLAUDE_SESSION_ID": "test-update"}
        _run_script("placeholder", env=env)
        sessions_root = tmp_path / "cerebro" / "cerebelo" / "sessoes"
        target = list(sessions_root.rglob("*-test-update.md"))[0]

        # Bypassa o throttle criando com mtime no passado
        os.utime(target, (time.time() - 10, time.time() - 10))

        payload = json.dumps({
            "session_id": "test-update",
            "tool": "Read",
            "args": "file=foo.py",
            "result": "ok",
        })
        result = _run_script("update", stdin=payload, env=env)
        assert result.returncode == 0

        content = target.read_text(encoding="utf-8")
        assert "tool=Read" in content
        assert "## Ações" in content
        # O bullet foi inserido DEPOIS do cabeçalho ## Ações
        actions_idx = content.index("## Ações")
        bullet_idx = content.index("tool=Read")
        assert bullet_idx > actions_idx

    def test_update_respects_throttle(self, tmp_path):
        env = {"SINAPSE_HOME": str(tmp_path), "CLAUDE_SESSION_ID": "test-throttle"}
        _run_script("placeholder", env=env)
        sessions_root = tmp_path / "cerebro" / "cerebelo" / "sessoes"
        target = list(sessions_root.rglob("*-test-throttle.md"))[0]

        # mtime AGORA (dentro do throttle)
        now = time.time()
        os.utime(target, (now, now))

        payload = json.dumps({"session_id": "test-throttle", "tool": "Read"})
        result = _run_script("update", stdin=payload, env=env)
        # Throttle: o script não escreve (mas retorna 0)
        content = target.read_text(encoding="utf-8")
        assert "tool=Read" not in content, "Throttle falhou — append feito dentro do intervalo"

    def test_update_ignores_consolidated_session(self, tmp_path):
        env = {"SINAPSE_HOME": str(tmp_path), "CLAUDE_SESSION_ID": "test-consol"}
        _run_script("placeholder", env=env)
        sessions_root = tmp_path / "cerebro" / "cerebelo" / "sessoes"
        target = list(sessions_root.rglob("*-test-consol.md"))[0]

        # Marca como consolidada
        text = target.read_text(encoding="utf-8")
        text = text.replace("---\n", "---\nconsolidated: true\n", 1)
        # Adiciona Resumo preenchido (>30 chars) na seção
        text = text.replace("## Resumo\n", "## Resumo\n\nResumo preenchido pelo consolidator de teste.\n")
        target.write_text(text, encoding="utf-8")
        os.utime(target, (time.time() - 100, time.time() - 100))

        payload = json.dumps({"session_id": "test-consol", "tool": "Read"})
        _run_script("update", stdin=payload, env=env)

        content = target.read_text(encoding="utf-8")
        # O update NÃO deve ter inserido mais um bullet após o Resumo
        assert content.count("tool=Read") == 0, "Update não respeitou consolidated: true"


class TestDailyWriter:
    """Agrega N sessões em 1 daily."""

    def test_daily_aggregates_sessions_no_llm(self, tmp_path):
        env = {"SINAPSE_HOME": str(tmp_path), "CLAUDE_SESSION_ID": "test-daily-1"}
        _run_script("placeholder", env=env)
        # Roda daily com --no-llm para o teste não chamar LLM
        result = _run_script("daily", "--no-llm", "--dry-run", env=env)
        assert result.returncode == 0
        # DRY_RUN imprime primeiras 500 chars
        assert "DRY_RUN" in result.stdout
        assert "Sessões encontradas" in result.stdout

    def test_daily_creates_file_with_session_links(self, tmp_path):
        env = {"SINAPSE_HOME": str(tmp_path), "CLAUDE_SESSION_ID": "test-daily-2"}
        _run_script("placeholder", env=env)
        result = _run_script("daily", "--no-llm", env=env)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        daily_root = tmp_path / "cerebro" / "cerebelo" / "diario"
        dailies = list(daily_root.rglob("*.md"))
        assert len(dailies) == 1, f"Esperava 1 daily, encontrei {len(dailies)}"
        content = dailies[0].read_text(encoding="utf-8")
        assert "type: daily-log" in content
        # Link para a session log
        assert "test-daily-2" in content
        assert "## Highlights" in content
        assert "## Aprendizados" in content
        # LLM pulado — placeholder visível
        assert "--no-llm" in content or "LLM pulado" in content


class TestAnatomicalPath:
    """Garante que usamos cerebro/cerebelo/ (não cerebro/cortex/cerebelo/ do doc)."""

    def test_paths_module_uses_cerebelo(self):
        from core import paths
        assert paths.CEREBELO.name == "cerebelo"
        # Path NÃO tem 'cortex' entre 'cerebro' e 'cerebelo'
        assert "cortex" not in str(paths.CEREBELO).replace("cerebro/cortex", "X")  # ignora match
        # ... mas o caminho REAL é cerebro/cerebelo (sem cortex)
        assert str(paths.CEREBELO).endswith("cerebro/cerebelo")

    def test_session_placeholder_uses_cerebelo_path(self):
        source = SCRIPTS["placeholder"].read_text(encoding="utf-8")
        assert "SESSIONS_ROOT" in source
        assert "cortex/cerebelo" not in source, "Bug: placeholder ainda referencia cortex/cerebelo"

    def test_daily_writer_uses_cerebelo_path(self):
        source = SCRIPTS["daily"].read_text(encoding="utf-8")
        assert "DAILY_ROOT" in source
        assert "cortex/cerebelo" not in source


class TestCanonicalRoles:
    """Garante que os 2 papéis novos estão registrados em core/auth.py."""

    def test_session_summarizer_is_canonical(self):
        source = (PROJECT_ROOT / "core" / "auth.py").read_text(encoding="utf-8")
        assert "session_summarizer" in source, "Papel session_summarizer ausente em HIVE_LLM_ROLES"
        assert "daily_writer" in source, "Papel daily_writer ausente em HIVE_LLM_ROLES"


class TestModelsExist:
    """SessionSummary e DailySummary devem existir."""

    def test_session_models_importable(self):
        from core.schemas.session_models import SessionSummary, DailySummary
        # Smoke: instanciar com payload mínimo
        s = SessionSummary(bullets=["x", "y"], decisions=[], open_questions=[])
        assert len(s.bullets) == 2
        d = DailySummary(highlights=["a"], learnings=["b"])
        assert len(d.learnings) == 1
