'use strict';
const fs = require('fs');
const { spawnSync } = require('child_process');
const { homeDir, which, isWSL, wslAvailableFromWindows } = require('./platform');

const REPO_URL = process.env.HIVE_MIND_REPO || 'https://github.com/Mlaurindo30/Hive-Mind.git';

const PREREQ_HINTS = {
  git: 'https://git-scm.com/downloads',
  curl: 'instale via gerenciador de pacotes do sistema',
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
    console.log('Windows nativo ainda usa o runtime via WSL2 (recomendado).');
    if (wslAvailableFromWindows()) {
      console.log('\nWSL detectado. Rode dentro do WSL:');
      console.log('  npx hive-sinapse-mind@latest init');
      console.log('\nModo nativo (beta): após um install em WSL ou manual, o supervisor');
      console.log('gerencia os serviços com `hive-mind services start` (ver README).');
    } else {
      console.log('\nInstale o WSL2 primeiro:  wsl --install');
      console.log('Depois, dentro do WSL:    npx hive-sinapse-mind@latest init');
    }
    return 1;
  }

  const missing = checkPrereqs();
  if (missing.length) {
    console.error('Pré-requisitos ausentes:');
    for (const m of missing) console.error(`  - ${m}: ${PREREQ_HINTS[m] || ''}`);
    return 1;
  }

  const dest = homeDir();
  if (!fs.existsSync(`${dest}/install.sh`)) {
    console.log(`Clonando Hive-Mind em ${dest}...`);
    const code = run('git', ['clone', '--depth', '1', REPO_URL, dest]);
    if (code !== 0) return code;
  } else {
    console.log(`Repositório já existe em ${dest} — usando o checkout atual.`);
  }

  const args = [`--profile=${profile}`];
  if (withTests) args.push('--with-tests');
  if (nonInteractive) args.push('--non-interactive');

  if (process.platform === 'darwin') {
    console.log('macOS: instalador principal + serviços via launchd (experimental).');
  } else if (isWSL()) {
    console.log('WSL detectado: caminho Linux padrão.');
  }

  console.log(`\nExecutando ./install.sh ${args.join(' ')} ...\n`);
  const code = run('bash', ['./install.sh', ...args], {
    cwd: dest,
    env: { ...process.env, ...env },
  });
  if (code === 0 && process.platform === 'darwin') {
    console.log('\nRegistrando LaunchAgents (macOS)...');
    run(`${dest}/.venv/bin/python`, ['scripts/setup/install_services.py', 'launchd'], { cwd: dest });
  }
  return code;
}

module.exports = { init, checkPrereqs, REPO_URL };
