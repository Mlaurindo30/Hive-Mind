from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _link(binary_dir: Path, name: str, target: str) -> None:
    (binary_dir / name).symlink_to(target)


def test_register_mcp_configures_three_project_local_codex_servers(tmp_path):
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
        ["/usr/bin/bash", str(ROOT / "scripts" / "register-mcp.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    config = json.loads((home / ".codex" / "mcp.json").read_text())
    servers = config["mcpServers"]
    assert set(servers) == {
        "sinapse-memory",
        "claude-mem-local",
        "neural-memory-local",
    }
    assert servers["sinapse-memory"]["command"] == str(ROOT / ".venv/bin/python")
    assert servers["claude-mem-local"]["args"] == [
        "-y",
        "claude-mem@13.6",
        "mcp-server",
    ]
    assert servers["neural-memory-local"]["command"] == str(
        ROOT / "scripts/neural-memory-local.sh"
    )

    commands = log.read_text().splitlines()
    assert any(line.startswith("mcp add sinapse-memory -- ") for line in commands)
    assert any(line.startswith("mcp add claude-mem-local -- ") for line in commands)
    assert any(line.startswith("mcp add neural-memory-local -- ") for line in commands)
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
            str(ROOT / "scripts" / "register-mcp.sh"),
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
    assert set(servers) >= {
        "sinapse-memory",
        "claude-mem-local",
        "neural-memory-local",
    }
    assert servers["sinapse-memory"]["type"] == "stdio"
    assert servers["claude-mem-local"]["type"] == "stdio"
    assert servers["neural-memory-local"]["type"] == "stdio"


def test_register_mcp_preserves_existing_entries_on_merge(tmp_path):
    home = tmp_path / "home"
    binary_dir = tmp_path / "bin"
    home.mkdir()
    binary_dir.mkdir()
    _link(binary_dir, "env", "/usr/bin/env")
    _link(binary_dir, "bash", "/usr/bin/bash")
    _link(binary_dir, "dirname", "/usr/bin/dirname")
    _link(binary_dir, "mkdir", "/usr/bin/mkdir")

    claude_cfg = home / ".claude" / ".mcp.json"
    claude_cfg.parent.mkdir(parents=True)
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
        "PROJECT_ROOT": str(ROOT),
    }
    subprocess.run(
        [
            "/usr/bin/bash",
            str(ROOT / "scripts" / "register-mcp.sh"),
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
    assert "custom-existing" in servers
    assert set(servers) >= {
        "custom-existing",
        "sinapse-memory",
        "claude-mem-local",
        "neural-memory-local",
    }
