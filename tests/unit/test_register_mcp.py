from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _link(binary_dir: Path, name: str, target: str) -> None:
    (binary_dir / name).symlink_to(target)


def test_register_mcp_configures_only_sinapse_memory_codex(tmp_path):
    home = tmp_path / "home"
    binary_dir = tmp_path / "bin"
    home.mkdir()
    binary_dir.mkdir()
    _link(binary_dir, "env", "/usr/bin/env")
    _link(binary_dir, "bash", "/usr/bin/bash")
    _link(binary_dir, "dirname", "/usr/bin/dirname")
    _link(binary_dir, "mkdir", "/usr/bin/mkdir")

    log = tmp_path / "codex.log"
    fake_codex = binary_dir / "codex"
    fake_codex.write_text(
        "#!/usr/bin/bash\n"
        'printf "%s\\n" "$*" >> "$FAKE_CODEX_LOG"\n'
        "exit 0\n"
    )
    fake_codex.chmod(0o755)

    env = {
        "HOME": str(home),
        "PATH": str(binary_dir),
        "FAKE_CODEX_LOG": str(log),
        "PROJECT_ROOT": str(ROOT),
    }
    result = subprocess.run(
        ["/usr/bin/bash", str(ROOT / "scripts" / "setup" / "register-mcp.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    # Modelo consolidado: só o orquestrador sinapse-memory é exposto ao agente
    # (ele federa NeuralMemory/claude-mem/Graphify/FalkorDB/UMC por dentro). Os
    # backends crus legados claude-mem-local/neural-memory-local NÃO são mais
    # registrados — register-mcp.sh os colapsa.
    config = json.loads((home / ".codex" / "mcp.json").read_text())
    servers = config["mcpServers"]
    assert set(servers) == {"sinapse-memory"}
    assert servers["sinapse-memory"]["command"] == str(ROOT / ".venv/bin/python")
    assert "claude-mem-local" not in servers
    assert "neural-memory-local" not in servers

    commands = log.read_text().splitlines()
    # O comando real é "mcp add sinapse-memory --env PYTHONPATH=... -- <python> <script>".
    # Os legados aparecem só em linhas "mcp remove ..." (limpeza), nunca em "mcp add".
    assert any(line.startswith("mcp add sinapse-memory") for line in commands)
    assert not any(line.startswith("mcp add claude-mem-local") for line in commands)
    assert not any(line.startswith("mcp add neural-memory-local") for line in commands)
    assert "Codex CLI" in result.stdout


def test_register_mcp_only_vscode_uses_servers_root_and_stdio(tmp_path):
    home = tmp_path / "home"
    binary_dir = tmp_path / "bin"
    project_root = tmp_path / "project"
    home.mkdir()
    binary_dir.mkdir()
    project_root.mkdir()
    (project_root / ".venv" / "bin").mkdir(parents=True)
    _link(project_root / ".venv" / "bin", "python", "/usr/bin/python3")
    _link(binary_dir, "env", "/usr/bin/env")
    _link(binary_dir, "bash", "/usr/bin/bash")
    _link(binary_dir, "dirname", "/usr/bin/dirname")
    _link(binary_dir, "mkdir", "/usr/bin/mkdir")

    env = {
        "HOME": str(home),
        "PATH": str(binary_dir),
        "PROJECT_ROOT": str(project_root),
    }
    subprocess.run(
        [
            "/usr/bin/bash",
            str(ROOT / "scripts" / "setup" / "register-mcp.sh"),
            "--only",
            "vscode",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    config = json.loads((project_root / ".vscode" / "mcp.json").read_text())
    servers = config["servers"]
    assert "sinapse-memory" in servers
    assert servers["sinapse-memory"]["type"] == "stdio"
    # Backends legados não são mais registrados (federados pelo sinapse-memory).
    assert "claude-mem-local" not in servers
    assert "neural-memory-local" not in servers


def test_register_mcp_preserves_existing_entries_on_merge(tmp_path):
    # Sem o CLI `claude` no PATH, do_claude() faz fallback e grava (merge) no
    # .mcp.json do PROJECT_ROOT (escopo project que o Claude Code lê). Usamos um
    # PROJECT_ROOT tmp p/ não tocar o repo real, com .venv/bin/python que o
    # merge_mcp_server usa para reescrever o JSON.
    home = tmp_path / "home"
    binary_dir = tmp_path / "bin"
    project_root = tmp_path / "project"
    home.mkdir()
    binary_dir.mkdir()
    project_root.mkdir()
    (project_root / ".venv" / "bin").mkdir(parents=True)
    _link(project_root / ".venv" / "bin", "python", "/usr/bin/python3")
    _link(binary_dir, "env", "/usr/bin/env")
    _link(binary_dir, "bash", "/usr/bin/bash")
    _link(binary_dir, "dirname", "/usr/bin/dirname")
    _link(binary_dir, "mkdir", "/usr/bin/mkdir")

    claude_cfg = project_root / ".mcp.json"
    claude_cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "custom-existing": {
                        "command": "echo",
                        "args": ["ok"],
                    }
                }
            }
        )
    )

    env = {
        "HOME": str(home),
        "PATH": str(binary_dir),
        "PROJECT_ROOT": str(project_root),
    }
    subprocess.run(
        [
            "/usr/bin/bash",
            str(ROOT / "scripts" / "setup" / "register-mcp.sh"),
            "--only",
            "claude",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    config = json.loads(claude_cfg.read_text())
    servers = config["mcpServers"]
    # Entradas de terceiros são preservadas no merge; sinapse-memory é adicionado;
    # os backends legados não entram (modelo federado consolidado).
    assert "custom-existing" in servers
    assert "sinapse-memory" in servers
    assert "claude-mem-local" not in servers
    assert "neural-memory-local" not in servers
