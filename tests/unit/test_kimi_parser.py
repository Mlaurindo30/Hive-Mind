"""Tests for legacy Kimi CLI and current Kimi Code session formats."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARSER = ROOT / "scripts" / "capture" / "parsers" / "kimi.py"
CAPTURE = ROOT / "scripts" / "capture"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))


def _load_parser():
    spec = importlib.util.spec_from_file_location("kimi_parser", PARSER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_kimi_code_reads_current_wire_format(tmp_path: Path) -> None:
    sid = "1e804ab4-be82-4d0f-9f72-d4d702a66051"
    session = tmp_path / f"session_{sid}"
    wire = session / "agents" / "main" / "wire.jsonl"
    wire.parent.mkdir(parents=True)
    (session / "state.json").write_text(json.dumps({"workDir": "D:/Hive-Mind"}), encoding="utf-8")
    records = [
        {
            "type": "turn.prompt",
            "input": [{"type": "text", "text": "prompt real"}],
            "origin": {"kind": "user"},
            "time": 1001,
        },
        {
            "type": "context.append_loop_event",
            "event": {
                "type": "tool.call",
                "toolCallId": "call-1",
                "name": "Read",
                "args": {"file_path": "README.md"},
            },
            "time": 1002,
        },
        {
            "type": "context.append_loop_event",
            "event": {
                "type": "tool.result",
                "toolCallId": "call-1",
                "result": {"output": "conteudo"},
            },
            "time": 1003,
        },
        {
            "type": "context.append_loop_event",
            "event": {"type": "content.part", "part": {"type": "text", "text": "resposta real"}},
            "time": 1004,
        },
    ]
    wire.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    parsed = _load_parser().parse(wire)[0]

    assert parsed["sid"] == sid
    assert parsed["prompts"] == ["prompt real"]
    assert parsed["prompt_events"] == [{
        "event_id": "1001",
        "content": "prompt real",
        "source_position": "wire.jsonl:time:1001",
    }]
    assert parsed["turns"] == [{
        "tool_name": "Read",
        "tool_input": {"file_path": "README.md"},
        "tool_response": "conteudo",
    }]
    assert parsed["last"] == "resposta real"
    assert parsed["cwd"] == "D:/Hive-Mind"