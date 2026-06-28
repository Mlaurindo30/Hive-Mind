import socket

from tests.real import service_registry as sr


def test_marker_services_defaults_to_ollama():
    assert sr.marker_services((), {}) == ("ollama",)


def test_marker_services_accepts_args_and_kwargs():
    assert sr.marker_services(("milvus",), {"services": ["falkordb", "claude-mem"]}) == (
        "milvus",
        "falkordb",
        "claude_mem",
    )


def test_unknown_service_is_explicit_error():
    status = sr.check_service("does-not-exist")
    assert status.unknown is True
    assert status.ok is False
    assert "conhecidos" in status.reason


def test_tcp_ok_against_real_local_socket():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        host, port = server.getsockname()
        assert sr.tcp_ok(host, port) is True
    finally:
        server.close()


def test_tcp_ok_closed_port_returns_false():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    host, port = server.getsockname()
    server.close()
    assert sr.tcp_ok(host, port, timeout=0.2) is False
