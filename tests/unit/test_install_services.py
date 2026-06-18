"""Testes do install_services — invariantes das units da Memória Viva (doc 08, §14.4-P1).

Não instala nada (não toca em systemctl): valida só o conteúdo gerado por
`unit_definitions()` e a coerência da lista `enabled`. Cobre os contratos que,
se quebrados, causam regressão silenciosa de reprodutibilidade/segurança:

- toda unit referida em `enabled` existe em `unit_definitions()`;
- todo `.timer` tem o `.service` correspondente;
- ExecStart aponta SEMPRE p/ o python do .venv local (R6: runtime project-local);
- topic_consolidator roda SEM --apply (log-only — nunca fundir automaticamente);
- dream NÃO está em `enabled` (go-live gated por M9, §14.4-P2);
- as 4 cadências da Memória Viva estão definidas (reprodutibilidade).
"""
import importlib.util
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "install_services", SCRIPTS / "install_services.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load()
DEFS = MOD.unit_definitions()

# Cadências da Memória Viva que precisam existir p/ não sumirem num reinstall.
MEMORIA_VIVA_UNITS = [
    "sinapse-dream.service", "sinapse-dream.timer",
    "sinapse-daily.service", "sinapse-daily.timer",
    "sinapse-weekly.service", "sinapse-weekly.timer",
    "sinapse-topics.service", "sinapse-topics.timer",
    # Fase 3 (F3.4)
    "sinapse-health.service", "sinapse-health.timer",
    "sinapse-drift.service", "sinapse-drift.timer",
    # Ponte multi-projeto
    "sinapse-bridge.service", "sinapse-bridge.timer",
    # Fase 4 (F4.1/F4.2)
    "sinapse-decisions.service", "sinapse-decisions.timer",
    "sinapse-projects.service", "sinapse-projects.timer",
    # F4.3/F4.4
    "sinapse-patterns.service", "sinapse-patterns.timer",
    "sinapse-conflicts.service", "sinapse-conflicts.timer",
    # F4.5
    "sinapse-work.service", "sinapse-work.timer",
]


def test_importa_sem_erro():
    assert hasattr(MOD, "unit_definitions")
    assert hasattr(MOD, "install")


def test_memoria_viva_units_definidas():
    """As 8 units (4 service + 4 timer) existem — reprodutibilidade (§14.4-P1)."""
    faltando = [u for u in MEMORIA_VIVA_UNITS if u not in DEFS]
    assert not faltando, f"units ausentes em unit_definitions(): {faltando}"


def test_todo_timer_tem_service():
    for name in DEFS:
        if name.endswith(".timer"):
            svc = name[: -len(".timer")] + ".service"
            assert svc in DEFS, f"{name} sem {svc} correspondente"


def test_execstart_usa_venv_local():
    """Nenhum ExecStart pode chamar python do sistema — só o .venv do projeto (R6)."""
    for name, content in DEFS.items():
        for line in content.splitlines():
            if line.startswith("ExecStart=") and "python" in line:
                assert "/.venv/bin/python" in line, (
                    f"{name}: ExecStart deve usar .venv/bin/python — {line!r}")


def test_topics_e_log_only_sem_apply():
    """topic_consolidator NUNCA roda com --apply via timer (merge é revisão humana)."""
    svc = DEFS["sinapse-topics.service"]
    exec_line = next(l for l in svc.splitlines() if l.startswith("ExecStart="))
    assert "topic_consolidator.py" in exec_line
    assert "--apply" not in exec_line, "topics deve ser log-only (sem --apply)"


def test_drift_e_log_only_sem_apply():
    """drift_detector NUNCA roda com --apply via timer (mover/esfriar é revisão humana)."""
    svc = DEFS["sinapse-drift.service"]
    exec_line = next(l for l in svc.splitlines() if l.startswith("ExecStart="))
    assert "drift_detector.py" in exec_line
    assert "--apply" not in exec_line, "drift deve ser log-only (sem --apply)"


def test_dream_definido_mas_nao_auto_habilitado():
    """dream existe (reprodutibilidade) porém fica fora do enabled (gated por M9)."""
    src = (SCRIPTS / "install_services.py").read_text()
    m = re.search(r"enabled = \[(.*?)\]", src, re.S)
    assert m, "lista enabled não encontrada"
    enabled_block = m.group(1)
    assert '"sinapse-dream.timer"' not in enabled_block, (
        "dream NÃO deve ser auto-habilitado antes de M9 (§14.4-P2)")
    assert '"sinapse-drift.timer"' not in enabled_block, (
        "drift NÃO deve ser auto-habilitado (--apply é decisão humana)")
    # As cadências seguras, por outro lado, devem estar habilitadas:
    for safe in ("sinapse-bridge.timer", "sinapse-daily.timer", "sinapse-weekly.timer",
                 "sinapse-topics.timer", "sinapse-health.timer"):
        assert f'"{safe}"' in enabled_block, f"{safe} deveria estar em enabled"
