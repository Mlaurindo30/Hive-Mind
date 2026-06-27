import json
import sys
import pytest
from pathlib import Path
import importlib.util

_mcp_path = Path(__file__).parent.parent.parent / "scripts" / "services" / "sinapse-mcp.py"
spec = importlib.util.spec_from_file_location("sinapse_mcp", _mcp_path)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class TestSinapseMCP:
    """Testes para scripts/services/sinapse-mcp.py (MCP server)"""

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
            "sinapse_temporal_timeline",
            "sinapse_temporal_get_observations",
            "sinapse_temporal_save",
            "sinapse_temporal_graph_search",
            "sinapse_zettelkasten_split",
            "sinapse_capture_screen",
            "sinapse_plan_goal",
            "sinapse_rag_query",
            "search_memories",
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
        assert "read_backends" in data
        assert "components" in data
        assert "vault" in data
        assert "plugin" in data
        assert "healthy" in data
        assert set(data["read_backends"]) == {
            "umc",
            "neural_memory",
            "sqlite_vec",
            "claude_mem",
            "graphify",
            "graphiti",
            "filesystem",
        }
        assert "rtk" not in data["read_backends"]
        assert "rtk" in data["components"]

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

    # ------------------------------------------------------------------
    # Passo 2: sinapse_query agora funde 7 backends via Context Fusion
    # ------------------------------------------------------------------

    def test_sinapse_query_description_lists_seven_backends(self):
        """A description da tool sinapse_query deve listar os 7 backends.

        Anatomia canônica: UMC + NeuralMemory + sqlite-vec + claude-mem
        + Graphify + Graphiti + filesystem. Se um backend for removido
        da anatomia, atualize a description explicitamente.
        """
        req = {"jsonrpc": "2.0", "id": 100, "method": "tools/list", "params": {}}
        resp = mcp.handle_request(req)
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        desc = tools["sinapse_query"]["description"]
        for backend in ("UMC", "NeuralMemory", "sqlite-vec", "claude-mem",
                        "Graphify", "Graphiti", "filesystem"):
            assert backend in desc, f"sinapse_query description missing: {backend}"

    def test_temporal_workflow_tools_are_described_in_order(self):
        """claude-mem temporal access must expose search -> timeline -> get_observations.

        If only search is exposed, agents get a shallow index and miss the full
        observation detail layer.
        """
        req = {"jsonrpc": "2.0", "id": 102, "method": "tools/list", "params": {}}
        resp = mcp.handle_request(req)
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        assert "Step 1" in tools["sinapse_temporal_search"]["description"]
        assert "Step 2" in tools["sinapse_temporal_timeline"]["description"]
        assert "Step 3" in tools["sinapse_temporal_get_observations"]["description"]

    def test_temporal_get_observations_posts_batch(self, monkeypatch):
        called = {}

        def fake_post(path, payload, timeout=5):
            called["path"] = path
            called["payload"] = payload
            called["timeout"] = timeout
            return {"source": "claude-mem (temporal)", "results": [{"id": 13834}]}

        monkeypatch.setattr(mcp, "_claude_mem_post", fake_post)
        result = mcp._temporal_get_observations({"ids": [13834]})
        assert called["path"] == "/api/observations/batch"
        assert called["payload"] == {"ids": [13834]}
        assert result["results"] == [{"id": 13834}]

    def test_sinapse_health_description_lists_seven_backends_and_excludes_rtk(self):
        """A description da tool sinapse_health deve listar os 7 read-backends
        E não mencionar RTK como backend (RTK é CLI proxy externo unrelated,
        não read-backend do cérebro).

        Guardrail para o acordo 9ea63d6: sinapse_health não pode herdar a
        confusão antiga que listava só 4 backends e incluía RTK no path
        de query. Se um backend for removido/adicionado, atualize esta lista.
        """
        req = {"jsonrpc": "2.0", "id": 101, "method": "tools/list", "params": {}}
        resp = mcp.handle_request(req)
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        desc = tools["sinapse_health"]["description"]
        for backend in ("UMC", "NeuralMemory", "sqlite-vec", "claude-mem",
                        "Graphify", "Graphiti", "filesystem"):
            assert backend in desc, f"sinapse_health description missing: {backend}"
        # RTK NÃO é read-backend — se aparecer, DEVE estar marcado claramente
        # como fora do path de query. Marcadores válidos:
        # - "CLI proxy", "CLI tool" (descrição técnica correta)
        # - "NOT a read-backend", "NOT a backend", "does NOT participate"
        # - "unrelated", "shell commands" (delimitando que é externo)
        # Nunca como backend listado.
        if "RTK" in desc:
            rtk_idx = desc.find("RTK")
            window = desc[max(0, rtk_idx - 80):rtk_idx + 100]
            exclusion_markers = (
                "CLI proxy", "CLI tool",
                "NOT a read-backend", "NOT a backend",
                "does NOT participate", "does not participate",
                "unrelated", "shell commands",
            )
            assert any(m in window for m in exclusion_markers), (
                f"RTK aparece em sinapse_health sem contexto de exclusão claro: "
                f"'...{window}...'. Se RTK for mencionado, deve estar marcado "
                "como não-read-backend do cérebro (CLI proxy externo, "
                "unrelated, agents install separately via 'rtk init')."
            )

    def test_sinapse_query_calls_query_vault_knowledge(self, monkeypatch):
        """_sinapse_query_with_diagnostics chama sm._query_vault_knowledge
        (orquestrador), nao sm._backend_umc (apenas UMC).

        Antes do Passo 2: `sinapse_query` chamava so UMC (1 backend) —
        quebrava a anatomia prometida. Agora deve chamar o orquestrador
        que funde os 7 backends.
        """
        # Importa o plugin via importlib (mesmo padrao do conftest em tests/integration/).
        import importlib.util as _il
        _plugin_path = Path(__file__).parent.parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
        if "sinapse_memory" not in sys.modules:
            _spec = _il.spec_from_file_location("sinapse_memory", _plugin_path)
            _mod = _il.module_from_spec(_spec)
            sys.modules["sinapse_memory"] = _mod
            _spec.loader.exec_module(_mod)
        sm = sys.modules["sinapse_memory"]
        # Monkeypatcha o orquestrador
        called = {}
        def _fake_orchestrator(query):
            called["query"] = query
            return {"source": "context-fusion", "observations": [
                {"content": "stub"}, {"content": "stub2"},
            ], "query": query, "backends_hit": 7}
        monkeypatch.setattr(sm, "_query_vault_knowledge", _fake_orchestrator)
        result = mcp._sinapse_query_with_diagnostics("hello")
        assert called.get("query") == "hello"
        assert result["source"] == "context-fusion"
        assert result["backends_hit"] == 7

    def test_sinapse_query_handles_all_backends_unhealthy(self, monkeypatch):
        """Quando o orquestrador retorna None (nenhum backend saudável),
        o MCP devolve um dict de erro estruturado (nao exception silenciosa).
        """
        import importlib.util as _il
        _plugin_path = Path(__file__).parent.parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
        if "sinapse_memory" not in sys.modules:
            _spec = _il.spec_from_file_location("sinapse_memory", _plugin_path)
            _mod = _il.module_from_spec(_spec)
            sys.modules["sinapse_memory"] = _mod
            _spec.loader.exec_module(_mod)
        sm = sys.modules["sinapse_memory"]
        monkeypatch.setattr(sm, "_query_vault_knowledge", lambda q: None)
        result = mcp._sinapse_query_with_diagnostics("hello")
        assert result["error_type"] == "BackendUnavailable"
        assert "nenhum backend saudável" in result["error"]

    def test_graphiti_backend_is_registered_in_plugin(self):
        """_backend_graphiti deve estar registrado em _READ_BACKENDS.

        Anatomia: Graphiti é um orgão do lobulo temporal. Sem o registro,
        o orquestrador do cerebro não funde Graphiti no sinapse_query.
        """
        import importlib.util as _il
        _plugin_path = Path(__file__).parent.parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
        if "sinapse_memory" not in sys.modules:
            _spec = _il.spec_from_file_location("sinapse_memory", _plugin_path)
            _mod = _il.module_from_spec(_spec)
            sys.modules["sinapse_memory"] = _mod
            _spec.loader.exec_module(_mod)
        sm = sys.modules["sinapse_memory"]
        assert hasattr(sm, "_backend_graphiti"), (
            "Plugin sinapse-memory deve expor _backend_graphiti (7o backend)"
        )
        assert sm._backend_graphiti in sm._READ_BACKENDS, (
            "_backend_graphiti deve estar registrado em _READ_BACKENDS"
        )
        assert sm._backend_graphiti in sm._READ_BACKENDS, (
            "_backend_graphiti deve estar registrado em _READ_BACKENDS"
        )
