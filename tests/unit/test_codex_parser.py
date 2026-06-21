from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARSER = ROOT / "scripts" / "capture" / "parsers" / "codex.py"


def _load_parser():
    spec = importlib.util.spec_from_file_location("codex_parser", PARSER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _line(kind: str, payload: dict) -> str:
    return json.dumps({"type": kind, "payload": payload})


def test_codex_parser_returns_all_user_prompts(tmp_path: Path) -> None:
    parser = _load_parser()
    session = tmp_path / "rollout-test.jsonl"
    session.write_text(
        "\n".join(
            [
                _line("session_meta", {"id": "ses-1", "cwd": "/work/Hive-Mind"}),
                _line(
                    "response_item",
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "primeiro prompt"}],
                    },
                ),
                _line(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "resposta"}],
                    },
                ),
                _line(
                    "response_item",
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "segundo prompt"}],
                    },
                ),
            ]
        )
    )

    parsed = parser.parse(session)

    assert len(parsed) == 1
    assert parsed[0]["prompt"] == "primeiro prompt"
    assert parsed[0]["prompts"] == ["primeiro prompt", "segundo prompt"]
