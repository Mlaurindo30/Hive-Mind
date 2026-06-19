"""F5.1 alert_dispatcher — testes unitários (doc 08 §11/F5.1).

Cobre: extração de alertas do snapshot, despacho idempotente,
contagem M13, dry-run vs apply, ausência de snapshot.
"""
import sys
import yaml
from datetime import datetime, date
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import alert_dispatcher as ad

NOW = datetime(2026, 6, 20, 9, 15, 30)
TODAY = NOW.date()


def _write_snapshot(saude: Path, *, alerts: list[str] | None = None) -> Path:
    saude.mkdir(parents=True, exist_ok=True)
    alert_block = (
        "\n".join(f"- ⚠️ {a}" for a in alerts) if alerts else "- ✅ Sem alertas."
    )
    content = (
        f"---\ntype: health-snapshot\ndate: {TODAY}\n---\n"
        f"# Saúde da Memória — {TODAY}\n\n"
        "## Métricas\n| Métrica | Valor |\n|---|---|\n\n"
        f"## Alertas\n{alert_block}\n"
    )
    p = saude / f"{TODAY.isoformat()}.md"
    p.write_text(content, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# load_alerts                                                                  #
# --------------------------------------------------------------------------- #

def test_load_sem_snapshot(tmp_path):
    assert ad.load_alerts(tmp_path / "nope", date=TODAY) == []


def test_load_sem_alertas(tmp_path):
    saude = tmp_path / "saude"
    _write_snapshot(saude, alerts=None)
    assert ad.load_alerts(saude, date=TODAY) == []


def test_load_extrai_alertas(tmp_path):
    saude = tmp_path / "saude"
    msgs = ["M2: só 2/7 daily logs (< 5).", "M4: órfãos em 18% (> 15%)."]
    _write_snapshot(saude, alerts=msgs)
    result = ad.load_alerts(saude, date=TODAY)
    assert result == msgs


def test_load_ignora_linha_verde(tmp_path):
    saude = tmp_path / "saude"
    # Snapshot com uma linha de alerta e uma linha OK misturada manualmente
    saude.mkdir(parents=True, exist_ok=True)
    p = saude / f"{TODAY.isoformat()}.md"
    p.write_text(
        "---\ntype: health-snapshot\n---\n"
        "## Alertas\n- ✅ Sem alertas.\n- ⚠️ M8: stale 50%.\n",
        encoding="utf-8",
    )
    result = ad.load_alerts(saude, date=TODAY)
    assert result == ["M8: stale 50%."]


# --------------------------------------------------------------------------- #
# dispatch                                                                     #
# --------------------------------------------------------------------------- #

def test_dispatch_dry_run_nao_cria_arquivos(tmp_path):
    inbox = tmp_path / "inbox"
    written = ad.dispatch(["M2: só 2/7 daily logs."], inbox, dry_run=True, now=NOW)
    assert len(written) == 1
    # dry-run: arquivo NÃO existe em disco
    assert not written[0].exists()


def test_dispatch_apply_cria_arquivo(tmp_path):
    inbox = tmp_path / "inbox"
    written = ad.dispatch(["M2: só 2/7 daily logs."], inbox, dry_run=False, now=NOW)
    assert len(written) == 1
    assert written[0].exists()


def test_dispatch_frontmatter_correto(tmp_path):
    inbox = tmp_path / "inbox"
    alert = "M4: órfãos em 18% (> 15%)."
    written = ad.dispatch([alert], inbox, dry_run=False, now=NOW)
    text = written[0].read_text(encoding="utf-8")
    m = __import__("re").match(r"^---\s*\n(.*?)\n---", text, __import__("re").DOTALL)
    assert m, "frontmatter ausente"
    fm = yaml.safe_load(m.group(1))
    assert fm["type"] == "health-alert"
    assert fm["metric"] == "M4"
    assert fm["severity"] == "warning"
    assert fm["message"] == alert
    assert fm["auto_resolved"] is False


def test_dispatch_path_correto(tmp_path):
    inbox = tmp_path / "inbox"
    written = ad.dispatch(["M2: teste."], inbox, dry_run=False, now=NOW)
    # inbox/2026/06/20/alerta-091530-{hash8}.md
    assert written[0].parent == inbox / "2026" / "06" / "20"
    assert written[0].name.startswith("alerta-091530-")
    assert written[0].name.endswith(".md")


def test_dispatch_idempotente(tmp_path):
    inbox = tmp_path / "inbox"
    alert = "M2: só 2/7 daily logs."
    first = ad.dispatch([alert], inbox, dry_run=False, now=NOW)
    assert len(first) == 1
    # segunda execução: mesmo hash → não recria
    second = ad.dispatch([alert], inbox, dry_run=False, now=NOW)
    assert len(second) == 0


def test_dispatch_vazio(tmp_path):
    inbox = tmp_path / "inbox"
    written = ad.dispatch([], inbox, dry_run=False, now=NOW)
    assert written == []


def test_dispatch_varios_alertas(tmp_path):
    inbox = tmp_path / "inbox"
    alerts = ["M2: só 2/7.", "M4: órfãos 20%.", "M8: stale 50%."]
    written = ad.dispatch(alerts, inbox, dry_run=False, now=NOW)
    assert len(written) == 3
    day_dir = inbox / "2026" / "06" / "20"
    assert len(list(day_dir.glob("alerta-*.md"))) == 3


# --------------------------------------------------------------------------- #
# m13_alerts_dispatched_today                                                  #
# --------------------------------------------------------------------------- #

def test_m13_zero_sem_inbox(tmp_path):
    assert ad.m13_alerts_dispatched_today(tmp_path / "nope", now=NOW) == 0


def test_m13_zero_sem_arquivos(tmp_path):
    inbox = tmp_path / "inbox"
    (inbox / "2026" / "06" / "20").mkdir(parents=True)
    assert ad.m13_alerts_dispatched_today(inbox, now=NOW) == 0


def test_m13_conta_alertas_despachados(tmp_path):
    inbox = tmp_path / "inbox"
    alerts = ["M2: só 2/7.", "M4: órfãos 20%."]
    ad.dispatch(alerts, inbox, dry_run=False, now=NOW)
    assert ad.m13_alerts_dispatched_today(inbox, now=NOW) == 2


def test_m13_ignora_outros_tipos(tmp_path):
    inbox = tmp_path / "inbox"
    day = inbox / "2026" / "06" / "20"
    day.mkdir(parents=True)
    # Arquivo com tipo diferente não é contado
    (day / "alerta-fake-12345678.md").write_text(
        "---\ntype: observation\n---\n", encoding="utf-8"
    )
    assert ad.m13_alerts_dispatched_today(inbox, now=NOW) == 0
