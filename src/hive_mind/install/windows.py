from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from hive_mind.install.fullstack_readiness import (
    test_fullstack_readiness,
    test_http_readiness,
)
from hive_mind.install.windows_prereqs import invoke_prerequisite_bootstrap
from hive_mind.install.snapshot import create_install_snapshot
from hive_mind.install.windows_launchers import ensure_gui_pythonw, validate_gui_launchers
from hive_mind.install.windows_support import (
    apply_profile_contract,
    ensure_python_runtime,
    project_uv_environment,
    read_dotenv,
    set_dotenv_value,
    sync_vault_templates,
)


VAULT_DIRS = [
    "cortex/temporal/_global",
    "cortex/temporal/hipocampo",
    "cortex/temporal/arquivo",
    "cortex/frontal/decisoes",
    "cortex/frontal/trabalho/active",
    "cortex/frontal/trabalho/ativo",
    "cortex/frontal/trabalho/arquivo",
    "cortex/frontal/projetos",
    "cortex/frontal/brain",
    "cortex/frontal/org/people",
    "cortex/frontal/org/teams",
    "cortex/parietal/inbox/visual",
    "cortex/parietal/inbox/documents",
    "cortex/parietal/referencias",
    "cortex/parietal/analises",
    "cortex/occipital/capturas-visuais",
    "cortex/occipital/grafo",
    "cortex/insula/saude",
    "cortex/insula/conflitos",
    "cerebelo/sessoes",
    "cerebelo/diario",
    "cerebelo/semanal",
    "cerebelo/padroes",
    "diencefalo/setores",
    "diencefalo/roteamento",
    "tronco/modelos",
    "tronco/paineis",
    "tronco/infra",
    "tronco/meta",
    "90-intake",
]



def _step(message: str) -> None:
    print(f"\n==> {message}")


def _find_command(name: str) -> str | None:
    path = shutil.which(name)
    return str(Path(path)) if path else None


def _find_bun() -> str | None:
    bun = _find_command("bun")
    if bun:
        return bun
    winget_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_root.is_dir():
        for candidate in winget_root.rglob("bun.exe"):
            return str(candidate)
    return None


def _find_cargo() -> str | None:
    cargo = _find_command("cargo")
    if cargo:
        return cargo
    candidate = Path.home() / ".cargo" / "bin" / "cargo.exe"
    return str(candidate) if candidate.is_file() else None


def _find_ollama() -> str | None:
    ollama = _find_command("ollama")
    if ollama:
        return ollama
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("ProgramFiles", ""))
    for candidate in (
        local / "Programs" / "Ollama" / "ollama.exe",
        local / "Ollama" / "ollama.exe",
        program_files / "Ollama" / "ollama.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _ensure_env_value(root: Path, name: str, value: str) -> None:
    set_dotenv_value(root, name, value)


def _apply_profile_contract(root: Path, profile_contract: Path) -> list[str]:
    return apply_profile_contract(root, profile_contract)


def _ensure_python_runtime(root: Path) -> None:
    ensure_python_runtime(root)


def _new_install_snapshot(root: Path) -> str:
    return str(create_install_snapshot(root, root / "backups").snapshot_path)


def _invoke_prerequisite_bootstrap(root: Path, profile: str, *, dry_run: bool = False) -> tuple[bool, bool, list[str]]:
    data = invoke_prerequisite_bootstrap(
        root=root,
        profile=profile,
        dry_run=dry_run,
    ).to_legacy_dict()
    return bool(data["Ready"]), bool(data["RestartRequired"]), list(data.get("Missing", []))


def _start_local_full_stack(root: Path) -> None:
    if not _find_command("docker"):
        raise SystemExit("docker was not found. Install Docker Desktop and keep it running for local-full.")
    docker_version = _run(["docker", "version"], cwd=root, check=False, capture=True)
    if docker_version.returncode != 0:
        raise SystemExit(
            "Docker is installed, but the Docker engine is not reachable. "
            "Start Docker Desktop and rerun the Python installer with --profile local-full."
        )

    _compose_stack(
        root,
        name="FalkorDB",
        compose_file=root / "docker-compose.falkordb.yml",
        containers=["sinapse-falkordb"],
    )
    _compose_stack(
        root,
        name="Milvus",
        compose_file=root / "integrations" / "milvus" / "docker-compose.yml",
        containers=["hive-mind-milvus"],
    )
    _compose_stack(
        root,
        name="RAGFlow",
        compose_file=root / "integrations" / "ragflow" / "docker-compose.yml",
        containers=["hive-mind-ragflow-mysql", "es01", "redis", "minio", "hive-mind-ragflow"],
    )

    if not test_http_readiness(
        "http://127.0.0.1:8384/rest/noauth/health",
        (200, 401, 403),
    ):
        syncthing = _find_command("syncthing")
        if syncthing:
            _run(
                [
                    syncthing,
                    "serve",
                    "--no-browser",
                    "--gui-address=127.0.0.1:8384",
                ],
                cwd=root,
                check=False,
            )

    for key, value in (
        ("VECTOR_BACKEND", "milvus"),
        ("MILVUS_URI", "http://localhost:19530"),
        ("HIVE_KNOWLEDGE_HEALTH_MILVUS", "1"),
        ("FALKORDB_HOST", "localhost"),
        ("FALKORDB_PORT", "6379"),
        ("RAGFLOW_BASE", "http://localhost:9380"),
    ):
        _ensure_env_value(root, key, value)

    data = test_fullstack_readiness(root=root, profile="local-full").to_legacy_dict()
    if not data["Ready"]:
        raise SystemExit(
            "local-full required services are not ready: "
            + ", ".join(data.get("Missing", []))
            + ". "
            + "; ".join(data.get("Diagnostics", []))
        )


def _compose_stack(root: Path, *, name: str, compose_file: Path, containers: list[str]) -> None:
    if not compose_file.is_file():
        raise SystemExit(f"{name} compose file was not found at {compose_file}")
    existing: list[str] = []
    for container in containers:
        inspected = _run(["docker", "container", "inspect", container], cwd=root, check=False)
        if inspected.returncode == 0:
            existing.append(container)
    if len(existing) == len(containers):
        print(f"Reusing existing {name} containers: {', '.join(containers)}")
        for container in containers:
            result = _run(["docker", "start", container], cwd=root, check=False)
            if result.returncode != 0:
                raise SystemExit(f"{name} container '{container}' could not be started.")
        return
    if existing:
        raise SystemExit(f"{name} has a partial existing container set ({', '.join(existing)}). Resolve it before rerunning installation.")
    print(f"Starting {name} from {compose_file}")
    result = _run(["docker", "compose", "-f", str(compose_file), "up", "-d", "--quiet-pull"], cwd=root, check=False)
    if result.returncode != 0:
        raise SystemExit(f"{name} docker compose startup failed.")


def _install_ollama_models(root: Path) -> None:
    ollama = _find_ollama()
    if not ollama:
        print("Ollama was not found; skipping local model download. Install Ollama and rerun the Python installer.", file=sys.stderr)
        return
    env_values = _parse_dotenv(root / ".env")
    models: set[str] = set()

    def add_model(model: str | None) -> None:
        if not model:
            return
        trimmed = model.strip()
        if trimmed and not trimmed.endswith(":cloud"):
            models.add(trimmed)

    add_model(env_values.get("OLLAMA_EMBED_MODEL", "snowflake-arctic-embed2:latest"))
    add_model(env_values.get("HIVE_GRAPHITI_MODEL", "qwen2.5:3b"))
    add_model(env_values.get("HIVE_LIGHTRAG_MODEL", "qwen2.5:3b"))
    for role in ("DREAMER", "GRAPHIFY", "VISION", "OCR", "SYNTHESIS", "CLAUDE_MEM"):
        for suffix in ("", "FALLBACK_", "FALLBACK2_"):
            provider = env_values.get(f"HIVE_{role}_{suffix}PROVIDER", "")
            model = env_values.get(f"HIVE_{role}_{suffix}MODEL", "")
            if provider.lower() == "ollama":
                add_model(model)
    if not models:
        print("No local Ollama models configured.")
        return
    print("Ensuring Ollama models: " + ", ".join(sorted(models)))
    for model in sorted(models):
        result = _run([ollama, "pull", model], cwd=root, check=False)
        if result.returncode != 0:
            raise SystemExit(result.returncode)


def _mark_safe_directories(root: Path) -> None:
    for component in ("graphify", "neural-memory", "rtk"):
        component_path = root / "integrations" / component
        if (component_path / ".git").exists():
            resolved = component_path.resolve().as_posix()
            result = _run(["git", "config", "--global", "--add", "safe.directory", resolved], cwd=root, check=False)
            if result.returncode != 0:
                raise SystemExit(f"Could not mark {component_path} as a trusted Git checkout.")


def _install_claude_mem_codex(root: Path) -> None:
    if not _find_command("npx"):
        print("npx not found; skipping claude-mem native installer.", file=sys.stderr)
        return
    bun = _find_bun()
    if not bun:
        print("bun not found; skipping claude-mem worker runtime install.", file=sys.stderr)
        return
    env = os.environ.copy()
    env["PATH"] = str(Path(bun).parent) + os.pathsep + env.get("PATH", "")
    env["CLAUDE_MEM_DATA_DIR"] = str(Path.home() / ".claude-mem")
    env["FASTEMBED_CACHE_PATH"] = str(Path.home() / ".claude-mem" / "models")
    Path(env["CLAUDE_MEM_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(env["FASTEMBED_CACHE_PATH"]).mkdir(parents=True, exist_ok=True)
    stdout = Path(os.environ.get("TEMP", str(root))) / "hive-mind-claude-mem-install.out.log"
    stderr = Path(os.environ.get("TEMP", str(root))) / "hive-mind-claude-mem-install.err.log"
    proc = subprocess.run(
        [
            "npx",
            "-y",
            "claude-mem@13.6",
            "install",
            "--ide",
            "codex-cli",
            "--runtime",
            "worker",
            "--provider",
            "claude",
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout.write_text(proc.stdout, encoding="utf-8")
    stderr.write_text(proc.stderr, encoding="utf-8")
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode != 0 and not _claude_mem_runtime_installed():
        raise SystemExit(proc.returncode)
    if proc.returncode != 0:
        print(
            f"claude-mem installer returned {proc.returncode}, but the worker and MCP runtime files are installed. Continuing.",
            file=sys.stderr,
        )


def _claude_mem_runtime_installed() -> bool:
    home = Path.home()
    cache_root = home / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem"
    known_roots = [
        home / ".claude" / "plugins" / "marketplaces" / "thedotmack" / "plugin" / "scripts",
        home / ".codex" / "plugins" / "cache" / "thedotmack" / "claude-mem" / "scripts",
        cache_root / "13.6.2" / "scripts",
        cache_root / "13.6.1" / "scripts",
        cache_root / "13.6.0" / "scripts",
    ]
    for known in known_roots:
        if (known / "worker-service.cjs").exists() and (known / "mcp-server.cjs").exists():
            return True
    if cache_root.is_dir():
        workers = list(cache_root.rglob("worker-service.cjs"))
        mcps = list(cache_root.rglob("mcp-server.cjs"))
        return bool(workers and mcps)
    return False


def _build_rtk(root: Path) -> None:
    rtk = root / "integrations" / "rtk" / "target" / "release" / "rtk.exe"
    if rtk.is_file():
        _run_passthrough([str(rtk), "--version"], cwd=root)
        return
    cargo = _find_cargo()
    if not cargo:
        print("cargo not found; install Rustup to compile RTK.", file=sys.stderr)
        return
    result = _run([cargo, "build", "--locked", "--release"], cwd=root / "integrations" / "rtk", check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _materialize_vault(root: Path) -> None:
    vault = root / "cerebro"
    sync_vault_templates(root)
    for rel in VAULT_DIRS:
        (vault / rel).mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hive-mind install windows")
    p.add_argument("--root", required=True)
    p.add_argument("--profile", choices=("local-min", "local-full"), default="local-min")
    p.add_argument("--force", action="store_true")
    p.add_argument("--with-tests", action="store_true")
    p.add_argument("--with-real-tests", action="store_true")
    p.add_argument("--skip-agents", action="store_true")
    p.add_argument("--skip-services", action="store_true")
    p.add_argument("--non-interactive", action="store_true")
    p.add_argument("--skip-prerequisites", action="store_true")
    p.add_argument("--prerequisites-only", action="store_true")
    p.add_argument("--install-prerequisites", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--repair", action="store_true")
    p.add_argument("--update", action="store_true")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--preserve-vault", action="store_true")
    p.add_argument("--preserve-database", action="store_true")
    p.add_argument("--system-service", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    profile_contract = root / "config" / "profiles" / f"{args.profile}.env.example"
    if not profile_contract.is_file():
        raise SystemExit(f"Profile contract was not found: {profile_contract}")
    if args.repair and args.uninstall:
        raise SystemExit("Repair and Uninstall cannot be combined.")
    if args.update and args.uninstall:
        raise SystemExit("Update and Uninstall cannot be combined.")

    if args.dry_run:
        print(f"Profile contract: {profile_contract}\n")
        print("==> Dry-run: validating prerequisite contract only")
        ready, _restart, missing = _invoke_prerequisite_bootstrap(root, args.profile, dry_run=True)
        print(f"Dry-run complete. Ready={ready}; Missing={', '.join(missing)}")
        return 0

    print("\n==> Protected memory snapshot")
    snapshot = _new_install_snapshot(root)
    print(f"Verified snapshot: {snapshot}")

    if (args.profile == "local-full" or args.install_prerequisites) and not args.skip_prerequisites:
        print("\n==> Host prerequisites")
        ready, restart_required, missing = _invoke_prerequisite_bootstrap(root, args.profile, dry_run=False)
        if restart_required:
            print(f"Windows restart required. Rerun the Python installer with --profile {args.profile}")
            return 3010
        if not ready:
            raise SystemExit("Required host prerequisites remain unavailable: " + ", ".join(missing))
    if args.prerequisites_only:
        return 0

    _step("Preflight")
    if not _find_command("uv"):
        raise SystemExit("uv was not found. Install uv: winget install Astral.UV")
    if not _find_command("git"):
        print("git was not found. scripts/setup/components.py bootstrap will need it for integrations.", file=sys.stderr)
    if not _find_command("node"):
        print("node was not found. The service supervisor and claude-mem install will be skipped.", file=sys.stderr)

    _step("Project virtual environment")
    if args.force and (root / ".venv").exists():
        raise SystemExit("-Force does not delete .venv automatically. Remove it yourself if you want a clean rebuild.")
    _ensure_python_runtime(root)

    _step("Environment file")
    env_path = root / ".env"
    if not env_path.exists():
        example = root / ".env.example"
        if example.is_file():
            shutil.copyfile(example, env_path)
        else:
            env_path.touch()
    applied = _apply_profile_contract(root, profile_contract)
    print("Applied profile defaults: " + ", ".join(applied))
    env_values = _parse_dotenv(env_path)
    if not env_values.get("HIVE_MIND_API_KEY"):
        _ensure_env_value(root, "HIVE_MIND_API_KEY", secrets.token_urlsafe(32))
    if args.profile == "local-full":
        _step("Local-full container stack")
        _start_local_full_stack(root)
    else:
        _ensure_env_value(root, "VECTOR_BACKEND", "sqlite_vec")

    os.environ.update(read_dotenv(root))

    _step("Ollama local models")
    _install_ollama_models(root)

    _step("Pinned integrations")
    if not _find_command("git"):
        raise SystemExit("git was not found. Install Git before bootstrapping pinned integrations.")
    _mark_safe_directories(root)
    _run_passthrough([sys.executable, str(root / "scripts" / "setup" / "components.py"), "bootstrap"], cwd=root)

    _step("Python dependencies with uv")
    _run_passthrough(
        ["uv", "sync", "--frozen", "--all-groups"],
        cwd=root,
        env=project_uv_environment(root),
    )
    ensure_gui_pythonw(root)
    validate_gui_launchers(root)
    _run_passthrough([str(root / ".venv" / "Scripts" / "python.exe"), "-c", "import pydantic, watchdog"], cwd=root)

    _step("Wrapper and UMC setup")
    verify_wrappers = [str(root / ".venv" / "Scripts" / "python.exe"), str(root / "scripts" / "setup" / "verify_wrappers.py")]
    if args.profile == "local-full":
        verify_wrappers.append("--require-docker")
    _run_passthrough(verify_wrappers, cwd=root)
    _run_passthrough([str(root / ".venv" / "Scripts" / "python.exe"), str(root / "scripts" / "setup" / "setup_umc.py")], cwd=root)

    _step("Vault materialization")
    _materialize_vault(root)

    project_python = str(root / ".venv" / "Scripts" / "python.exe")

    _step("Graph/index bootstrap")
    _run_passthrough([project_python, "-m", "graphify", "update", str(root / "cerebro")], cwd=root)

    if not args.skip_agents:
        _step("MCP registration")
        _run_passthrough(
            [project_python, "-m", "hive_mind.cli", "agents", "register", "--apply", "--instructions", "--project-root", str(root)],
            cwd=root,
        )

    if not args.skip_services and _find_command("node"):
        _step("claude-mem native runtime")
        _install_claude_mem_codex(root)

        _step("RTK")
        _build_rtk(root)

        _step("Services")
        _run_passthrough([project_python, "-m", "hive_mind.cli", "service", "manifest", "--json"], cwd=root)
        env = os.environ.copy()
        env["HIVE_MIND_HOME"] = str(root)
        _run_passthrough(["node", str(root / "npm" / "bin" / "hive-mind.js"), "services", "restart"], cwd=root, env=env)
        _run_passthrough(["node", str(root / "npm" / "bin" / "hive-mind.js"), "services", "wait"], cwd=root, env=env)
        _run_passthrough(["node", str(root / "npm" / "bin" / "hive-mind.js"), "services", "status"], cwd=root, env=env)

    if not args.skip_services:
        _step("Scheduled knowledge jobs (Task Scheduler)")
        _run_passthrough([project_python, "-m", "hive_mind.cli", "service", "windows-jobs", "--apply", "--project-root", str(root)], cwd=root)

        _step("Windows autostart")
        _run_passthrough([project_python, "-m", "hive_mind.cli", "service", "windows-runtime", "--apply", "--project-root", str(root)], cwd=root)

    if args.with_tests:
        _step("Tests")
        _run_passthrough([project_python, "-m", "pytest", "tests/unit", "tests/integration", "tests/e2e", "-v"], cwd=root)

    if args.with_real_tests:
        _step("Real knowledge tests")
        report = root / "logs" / "real-knowledge-report.xml"
        report.parent.mkdir(parents=True, exist_ok=True)
        _run_passthrough([project_python, "-m", "pytest", "tests/real", "-m", "real", "-v", "--timeout=1200", f"--junitxml={report}"], cwd=root)

    _step("Done")
    print(f"Hive-Mind Windows install finished in {root}")
    return 0
