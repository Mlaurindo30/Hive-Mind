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

function init(options) {
  const { profile = 'local-min', withTests = false, nonInteractive = true, env = {} } = options;

  if (process.platform === 'win32') {
    console.log('Windows native still uses the runtime via WSL2 (recommended).');
    if (wslAvailableFromWindows()) {
      console.log('\nWSL detected. Run inside WSL:');
      console.log('  npx hive-sinapse-mind@latest init');
      console.log('\nNative mode (beta): after an install in WSL or manual, the supervisor');
      console.log('manages services with `hive-mind services start` (see README).');
    } else {
      console.log('\nInstall WSL2 first:  wsl --install');
      console.log('Then, inside WSL:    npx hive-sinapse-mind@latest init');
    }
    return 1;
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
