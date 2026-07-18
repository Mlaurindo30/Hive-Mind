"""Tests for Qwen Code CLI/desktop JSONL session format."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARSER = ROOT / "scripts" / "capture" / "parsers" / "qwen.py"
CAPTURE = ROOT / "scripts" / "capture"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))


def _load_parser():
    spec = importlib.util.spec_from_file_location("qwen_parser", PARSER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_qwen_reads_real_chat_jsonl_format(tmp_path: Path) -> None:
    sid = "3eb6adb1-d3c1-4f63-982e-78b423b1b649"
    chat = tmp_path / "projects" / "workspace" / "chats" / f"{sid}.jsonl"
    chat.parent.mkdir(parents=True)
    records = [
        {
            "uuid": "prompt-event",
            "sessionId": sid,
            "timestamp": "2026-07-18T00:55:50.493Z",
            "type": "user",
            "cwd": "D:/Hive-Mind",
            "message": {"role": "user", "parts": [{"text": "prompt real"}]},
        },
        {
            "uuid": "assistant-event",
            "sessionId": sid,
            "timestamp": "2026-07-18T00:55:54.523Z",
            "type": "assistant",
            "cwd": "D:/Hive-Mind",
            "message": {"role": "model", "parts": [{"text": "resposta real"}]},
        },
    ]
    chat.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    parsed = _load_parser().parse(chat)[0]

    assert parsed["sid"] == sid
    assert parsed["prompts"] == ["prompt real"]
    assert parsed["prompt_events"] == [{
        "event_id": "prompt-event",
        "content": "prompt real",
        "source_position": f"{sid}.jsonl:uuid:prompt-event",
    }]
    assert parsed["turns"] == [{
        "tool_name": "Message",
        "tool_input": {"prompt": "prompt real"},
        "tool_response": "resposta real",
    }]
    assert parsed["last"] == "resposta real"
    assert parsed["cwd"] == "D:/Hive-Mind"