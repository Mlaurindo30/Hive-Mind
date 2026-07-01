from pathlib import Path

import scripts.health.audit_memory as audit_memory


def test_split_excludes_combines_repeated_csv_and_env(monkeypatch):
    monkeypatch.setenv("SINAPSE_AUDIT_EXCLUDE", "ProjetoC, ProjetoD/*")

    patterns = audit_memory._split_excludes(["ProjetoA", "ProjetoB/*, ProjetoB2"])

    assert patterns == ["ProjetoA", "ProjetoB/*", "ProjetoB2", "ProjetoC", "ProjetoD/*"]


def test_is_excluded_matches_temporal_prefix_and_glob(monkeypatch, tmp_path):
    root = tmp_path / "Hive-Mind"
    temporal = root / "cerebro" / "cortex" / "temporal"
    target = temporal / "ProjetoA" / "topic" / "neuronio-x.md"
    other = temporal / "ProjetoB" / "topic" / "neuronio-y.md"
    target.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    target.write_text("# x\n", encoding="utf-8")
    other.write_text("# y\n", encoding="utf-8")
    monkeypatch.setattr(audit_memory, "SINAPSE_HOME", str(root))

    assert audit_memory._is_excluded(target, ["ProjetoA"])
    assert audit_memory._is_excluded(target, ["ProjetoA/*"])
    assert not audit_memory._is_excluded(other, ["ProjetoA"])
