import json

import pytest

from scripts.setup.components import load_lock


def _write_lock(path, components):
    path.write_text(
        json.dumps({"schema_version": 1, "components": components}),
        encoding="utf-8",
    )


def test_components_lock_rejects_wrapper_components(tmp_path):
    lock = tmp_path / "components.lock.json"
    _write_lock(
        lock,
        {
            "graphify": {
                "repository": "https://example.invalid/graphify.git",
                "commit": "abc",
                "version": "test",
            },
            "milvus": {
                "repository": "https://example.invalid/milvus.git",
                "commit": "def",
                "version": "test",
            },
        },
    )

    with pytest.raises(SystemExit, match="ADR-018"):
        load_lock(lock)


def test_components_lock_accepts_pinned_clone_components(tmp_path):
    lock = tmp_path / "components.lock.json"
    _write_lock(
        lock,
        {
            "graphify": {
                "repository": "https://example.invalid/graphify.git",
                "commit": "abc",
                "version": "test",
            }
        },
    )

    data = load_lock(lock)

    assert "graphify" in data["components"]
