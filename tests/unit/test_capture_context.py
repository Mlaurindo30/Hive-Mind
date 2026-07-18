from __future__ import annotations

from scripts.capture.capture_events import ProviderEvent
from scripts.capture.session_events import session_to_events


def test_provider_event_preserves_context_in_queue_payload() -> None:
    event = ProviderEvent.create(
        "antigravity",
        "session-1",
        "prompt",
        "analisar parser",
        event_id="native-prompt-1",
        project="D:/Hive-Mind",
        cwd="D:/Hive-Mind/scripts/capture",
        metadata={"source": "transcript_full.jsonl", "step_index": 7},
    )

    payload = event.as_payload()

    assert payload["project"] == "D:/Hive-Mind"
    assert payload["cwd"] == "D:/Hive-Mind/scripts/capture"
    assert payload["metadata"] == {"source": "transcript_full.jsonl", "step_index": 7}


def test_parser_session_context_reaches_normalized_events() -> None:
    events = session_to_events(
        "antigravity",
        {
            "sid": "session-1",
            "project": "D:/Hive-Mind",
            "cwd": "D:/Hive-Mind/scripts/capture",
            "prompt_events": [
                {
                    "content": "corrigir captura",
                    "event_id": "native-prompt-1",
                    "source_position": "step:7",
                    "metadata": {"step_index": 7},
                }
            ],
        },
    )

    assert len(events) == 1
    assert events[0].project == "D:/Hive-Mind"
    assert events[0].cwd == "D:/Hive-Mind/scripts/capture"
    assert events[0].metadata == {"step_index": 7}
