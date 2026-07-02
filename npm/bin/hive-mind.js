#!/usr/bin/env node
'use strict';
const path = require('path');
const { spawnSync } = require('child_process');
const pkg = require('../package.json');
const { homeDir, which } = require('../lib/platform');

const HELP = `hive-mind v${pkg.version} — local-first memory for AI agents

Usage: hive-mind <command> [options]

Commands:
  init [--profile=local-min|local-full] [--with-tests]
                     Clone and install Hive-Mind (Linux/WSL/macOS)
  init wizard        Interactive installation wizard
  doctor             Health check of the runtime (API, services)
  services start|stop|status|restart
                     Manage services (systemd/launchd/supervisor)
  mcp register --agent <claude|codex|gemini|cursor|...>
                     Register the sinapse-memory MCP server in the agent
  update             Update the checkout (git pull) and reinstall services
  version            Show the version
  help               This help

Installation directory: $HIVE_MIND_HOME (default ~/Hive-Mind)
Service backend:        systemd (Linux/WSL) · launchd (macOS) ·
                        Node supervisor (Windows / HIVE_MIND_SUPERVISOR=1)
`;

function parseFlags(argv) {
  const flags = {};
  const rest = [];
  for (const a of argv) {
    const m = /^--([a-z-]+)(?:=(.*))?$/.exec(a);
    if (m) flags[m[1]] = m[2] ?? true;
    else rest.push(a);
  }
  return { flags, rest };
}

function doctor() {
  const root = homeDir();
  console.log(`Hive-Mind at: ${root}`);
  const health = spawnSync('curl', ['-s', '--max-time', '3', 'http://127.0.0.1:37702/api/v1/health'], { encoding: 'utf8' });
  console.log(`API :37702 → ${health.stdout || 'offline'}`);
  const { dispatch } = require('../lib/services');
  return dispatch('status');
}

function mcpRegister(flags) {
  const agent = flags.agent;
  if (!agent) {
    console.error('usage: hive-mind mcp register --agent <claude|codex|gemini|cursor|...>');
    return 1;
  }
  return spawnSync('bash', ['./scripts/setup/register-mcp.sh', '--only', String(agent)], {
    cwd: homeDir(),
    stdio: 'inherit',
  }).status ?? 1;
}

function update() {
  const root = homeDir();
  let code = spawnSync('git', ['-C', root, 'pull', '--ff-only'], { stdio: 'inherit' }).status ?? 1;
  if (code !== 0) return code;
  if (process.platform === 'win32') return 0;
  const py = path.join(root, '.venv', 'bin', 'python');
  if (which('uv')) {
    code = spawnSync('uv', ['sync', '--frozen', '--all-groups'], { cwd: root, stdio: 'inherit' }).status ?? code;
  }
  return spawnSync(py, ['scripts/setup/install_services.py', 'install'], { cwd: root, stdio: 'inherit' }).status ?? code;
}

async function main() {
  const [, , cmd, ...argv] = process.argv;
  const { flags, rest } = parseFlags(argv);

  switch (cmd) {
    case 'init': {
      if (rest[0] === 'wizard') {
        const { wizard } = require('../lib/wizard');
        return wizard();
      }
      const { init } = require('../lib/init');
      return init({
        profile: flags.profile || 'local-min',
        withTests: Boolean(flags['with-tests']),
        nonInteractive: true,
      });
    }
    case 'doctor':
      return doctor();
    case 'services': {
      const action = rest[0];
      if (!['start', 'stop', 'status', 'restart'].includes(action)) {
        console.error('usage: hive-mind services start|stop|status|restart');
        return 1;
      }
      const { dispatch } = require('../lib/services');
      return dispatch(action);
    }
    case 'mcp':
      if (rest[0] === 'register') return mcpRegister(flags);
      console.error('usage: hive-mind mcp register --agent <name>');
      return 1;
    case 'update':
      return update();
    case 'version':
    case '--version':
    case '-v':
      console.log(pkg.version);
      return 0;
    case 'help':
    case '--help':
    case '-h':
    case undefined:
      console.log(HELP);
      return 0;
    default:
      console.error(`unknown command: ${cmd}\n`);
      console.log(HELP);
      return 1;
  }
}

main().then(
  (code) => process.exit(code ?? 0),
  (err) => {
    console.error(err.message || err);
    process.exit(1);
  }
);
