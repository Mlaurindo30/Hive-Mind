'use strict';
const fs = require('fs');
const { spawnSync } = require('child_process');
const { homeDir, which, isWSL, wslAvailableFromWindows } = require('./platform');

const REPO_URL = process.env.HIVE_MIND_REPO || 'https://github.com/Mlaurindo30/Hive-Mind.git';

const PREREQ_HINTS = {
  git: 'https://git-scm.com/downloads',
  curl: 'install via the system package manager',
  uv: 'curl -LsSf https://astral.sh/uv/install.sh | sh',
  bun: 'curl -fsSL https://bun.sh/install | bash',
};

function checkPrereqs() {
  const missing = [];
  for (const cmd of ['git', 'curl', 'uv', 'bun']) {
    if (!which(cmd)) missing.push(cmd);
  }
  return missing;
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  if (r.error) throw r.error;
  return r.status ?? 1;
}

// ---------------------------------------------------------------------------
// Windows native bootstrap (beta)
// ---------------------------------------------------------------------------
// Agents on Windows (Claude Code, Cursor, Copilot) run on the HOST — a WSL2
// install lives in another filesystem/network namespace and their MCP configs
// cannot reach it. Native mode performs the core of install.sh with
// cross-platform tools: uv sync, vault from templates, .env, MCP registration
// and services via the Node supervisor (systemd-free).
const path = require('path');
const os = require('os');

function mergeMcpConfig(file, servers) {
  let current = {};
  try { current = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { /* novo */ }
  current.mcpServers = { ...(current.mcpServers || {}), ...servers };
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(current, null, 2) + '\n');
  console.log(`  MCP: ${file}`);
}

function nativeWindowsInit(dest) {
  console.log('Windows NATIVE mode (beta) — services via Node supervisor.');

  const missing = [];
  for (const cmd of ['git', 'uv']) if (!which(cmd)) missing.push(cmd);
  if (missing.length) {
    console.error('Missing prerequisites (native mode):');
    for (const m of missing) console.error(`  - ${m}: ${PREREQ_HINTS[m] || ''}`);
    if (wslAvailableFromWindows()) {
      console.error('\nAlternative: run inside WSL2 (npx hive-sinapse-mind@latest init),');
      console.error('but note that HOST agents cannot reach a WSL-only install.');
    }
    return 1;
  }
  if (!which('bun')) {
    console.warn('warn: bun not found — the claude-mem worker will be skipped by the supervisor.');
  }

  if (!fs.existsSync(`${dest}/install.sh`)) {
    console.log(`Cloning Hive-Mind into ${dest}...`);
    const code = run('git', ['clone', '--depth', '1', REPO_URL, dest]);
    if (code !== 0) return code;
  } else {
    console.log(`Repository already exists at ${dest} — using the current checkout.`);
  }

  console.log('\nPython deps: uv sync --frozen --all-groups ...');
  let code = run('uv', ['sync', '--frozen', '--all-groups'], { cwd: dest });
  if (code !== 0) return code;

  const vault = path.join(dest, 'cerebro');
  if (!fs.existsSync(vault)) {
    const tpl = path.join(dest, 'templates', 'vault');
    if (fs.existsSync(tpl)) {
      console.log('Materializing vault from templates/vault ...');
      fs.cpSync(tpl, vault, { recursive: true });
    } else {
      fs.mkdirSync(vault, { recursive: true });
    }
  }

  const envFile = path.join(dest, '.env');
  if (!fs.existsSync(envFile)) {
    let example = fs.readFileSync(path.join(dest, '.env.example'), 'utf8');
    // Fresh install without Docker: sqlite_vec (same rule as install.sh).
    example = example.replace(/^VECTOR_BACKEND=milvus/m, 'VECTOR_BACKEND=sqlite_vec');
    fs.writeFileSync(envFile, example);
    console.log('.env created from .env.example (VECTOR_BACKEND=sqlite_vec).');
  }

  // MCP registration for host agents (JSON configs; equivalent of register-mcp.sh).
  const venvPy = path.join(dest, '.venv', 'Scripts', 'python.exe');
  const tplJson = JSON.parse(
    fs.readFileSync(path.join(dest, 'config', 'mcp', 'sinapse-memory.json'), 'utf8')
  );
  const server = tplJson.mcpServers['sinapse-memory'];
  server.command = venvPy;
  server.args = server.args.map((a) => a.replace('PROJECT_ROOT_PLACEHOLDER', dest));
  server.cwd = dest;
  const servers = { 'sinapse-memory': server };
  mergeMcpConfig(path.join(dest, '.mcp.json'), servers);                      // Claude Code (project)
  mergeMcpConfig(path.join(os.homedir(), '.cursor', 'mcp.json'), servers);    // Cursor
  mergeMcpConfig(path.join(os.homedir(), '.codex', 'mcp.json'), servers);     // Codex CLI

  console.log('\nStarting services via supervisor...');
  const supervisor = require('./supervisor');
  code = supervisor.start();

  console.log('\nNative install (beta) finished.');
  console.log('  - status:   hive-mind services status');
  console.log('  - doctor:   hive-mind doctor');
  console.log('  - limitation: .sh-based services are skipped on native Windows.');
  return code;
}

function init(options) {
  const { profile = 'local-min', withTests = false, nonInteractive = true, env = {} } = options;

  if (process.platform === 'win32') {
    return nativeWindowsInit(homeDir());
  }

  const missing = checkPrereqs();
  if (missing.length) {
    console.error('Missing prerequisites:');
    for (const m of missing) console.error(`  - ${m}: ${PREREQ_HINTS[m] || ''}`);
    return 1;
  }

  const dest = homeDir();
  if (!fs.existsSync(`${dest}/install.sh`)) {
    console.log(`Cloning Hive-Mind into ${dest}...`);
    const code = run('git', ['clone', '--depth', '1', REPO_URL, dest]);
    if (code !== 0) return code;
  } else {
    console.log(`Repository already exists at ${dest} — using the current checkout.`);
  }

  const args = [`--profile=${profile}`];
  if (withTests) args.push('--with-tests');
  if (nonInteractive) args.push('--non-interactive');

  if (process.platform === 'darwin') {
    console.log('macOS: main installer + services via launchd (experimental).');
  } else if (isWSL()) {
    console.log('WSL detected: standard Linux path.');
  }

  console.log(`\nRunning ./install.sh ${args.join(' ')} ...\n`);
  const code = run('bash', ['./install.sh', ...args], {
    cwd: dest,
    env: { ...process.env, ...env },
  });
  if (code === 0 && process.platform === 'darwin') {
    console.log('\nRegistering LaunchAgents (macOS)...');
    run(`${dest}/.venv/bin/python`, ['scripts/setup/install_services.py', 'launchd'], { cwd: dest });
  }
  return code;
}

module.exports = { init, checkPrereqs, REPO_URL };
