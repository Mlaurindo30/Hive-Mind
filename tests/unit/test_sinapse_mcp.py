import json
import sys
import pytest
from pathlib import Path
import importlib.util

_mcp_path = Path(__file__).parent.parent.parent / "scripts" / "sinapse-mcp.py"
spec = importlib.util.spec_from_file_location("sinapse_mcp", _mcp_path)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class TestSinapseMCP:
    """Testes para scripts/sinapse-mcp.py (MCP server)"""

    def test_initialize_response(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = mcp.handle_request(req)
        assert resp is not None
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "sinapse-memory"

    def test_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = mcp.handle_request(req)
        tools = resp["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "sinapse_query",
            "sinapse_save_decision",
            "sinapse_save_learning",
            "sinapse_health",
            "sinapse_session_end",
            "sinapse_temporal_search",
            "sinapse_temporal_save",
            "sinapse_zettelkasten_split",
            "sinapse_capture_screen",
        }

    def test_health_tool(self):
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "sinapse_health", "arguments": {}}
        }
        resp = mcp.handle_request(req)
        assert "content" in resp["result"]
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert "backends" in data
        assert "vault" in data
        assert "plugin" in data
        assert "healthy" in data

    def test_query_tool(self):
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "sinapse_query", "arguments": {"query": "thoth"}}
        }
        resp = mcp.handle_request(req)
        assert "content" in resp["result"]
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert isinstance(data, dict)

    def test_save_decision_tool_dryrun(self, temp_vault, monkeypatch):
        monkeypatch.setenv("SINAPSE_HOME", temp_vault)
        monkeypatch.setenv("SINAPSE_DRY_RUN", "1")
        req = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "sinapse_save_decision",
                "arguments": {"title": "MCP Decision", "content": "Test from MCP"}
            }
        }
        resp = mcp.handle_request(req)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert "saved" in data

    def test_save_learning_tool_dryrun(self, temp_vault, monkeypatch):
        monkeypatch.setenv("SINAPSE_HOME", temp_vault)
        monkeypatch.setenv("SINAPSE_DRY_RUN", "1")
        req = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "sinapse_save_learning",
                "arguments": {"title": "MCP Pattern", "content": "Learning from MCP"}
            }
        }
        resp = mcp.handle_request(req)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert "saved" in data

    def test_unknown_tool_returns_error(self):
        req = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        }
        resp = mcp.handle_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_unknown_method_returns_error(self):
        req = {"jsonrpc": "2.0", "id": 8, "method": "unknown/method"}
        resp = mcp.handle_request(req)
        assert "error" in resp

    def test_notification_returns_none(self):
        req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = mcp.handle_request(req)
        assert resp is None

    def test_each_tool_has_input_schema(self):
        req = {"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}}
        resp = mcp.handle_request(req)
        for tool in resp["result"]["tools"]:
            assert "inputSchema" in tool
            assert "name" in tool
            assert "description" in tool
