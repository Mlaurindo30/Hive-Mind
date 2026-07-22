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

function windowsInstallerArgs(options = {}, root = path.resolve(__dirname, '..', '..')) {
  const args = ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'install.ps1')];
  args.push('-Profile', options.profile || 'local-min');
  if (options.withTests) args.push('-WithTests');
  if (options.nonInteractive) args.push('-NonInteractive');
  if (options.installPrerequisites) args.push('-InstallPrerequisites');
  if (options.dryRun) args.push('-DryRun');
  return args;
}

function mergeMcpConfig(file, servers) {
  let current = {};
  try { current = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { /* novo */ }
  current.mcpServers = { ...(current.mcpServers || {}), ...servers };
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(current, null, 2) + '\n');
  console.log(`  MCP: ${file}`);
}

function nativeWindowsInit(dest, options = {}) {
  console.log('Windows native mode — delegating to install.ps1.');
  if (!fs.existsSync(path.join(dest, 'install.ps1'))) {
    console.log(`Cloning Hive-Mind into ${dest}...`);
    const code = run('git', ['clone', '--depth', '1', REPO_URL, dest]);
    if (code !== 0) return code;
  }
  return run('powershell.exe', windowsInstallerArgs(options, dest), { cwd: dest });
}
function init(options) {
  const { profile = 'local-min', withTests = false, nonInteractive = true, env = {} } = options;

  if (process.platform === 'win32') {
    return nativeWindowsInit(homeDir(), { profile, withTests, nonInteractive });
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

module.exports = { init, checkPrereqs, REPO_URL, windowsInstallerArgs };
