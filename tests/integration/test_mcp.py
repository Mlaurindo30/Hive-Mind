import pytest
from sinapse_memory import health_check, _READ_BACKENDS


class TestMCP:
    """I3: Testes de interface MCP/plugin"""

    def test_backends_registered(self):
        """I3.1: Backends estão registrados."""
        assert len(_READ_BACKENDS) >= 1

    def test_health_check_plugin_count(self):
        """I3.2: health_check reflete backends_registered."""
        status = health_check()
        assert status["plugin"]["backends_registered"] >= 1

    def test_health_check_vault_path(self):
        """I3.3: health_check reporta path do vault."""
        status = health_check()
        assert "path" in status["vault"]
        assert status["vault"]["path"]
