'use strict';
// F3 — Cross-platform supervisor: manages services from the manifest
// (install_services.py manifest) as child processes with auto-restart.
// It is the service backend where systemd/launchd is unavailable (Windows native)
// and can be forced on any OS with HIVE_MIND_SUPERVISOR=1.
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { homeDir } = require('./platform');

function paths() {
  const root = homeDir();
  const dir = path.join(root, 'logs', 'supervisor');
  return {
    root,
    dir,
    manifest: path.join(dir, 'manifest.json'),
    pidFile: (name) => path.join(dir, `${name}.pid`),
    logFile: (name) => path.join(dir, `${name}.log`),
    daemonPid: path.join(dir, 'supervisor.pid'),
    daemonLog: path.join(dir, 'supervisor.log'),
  };
}

function pythonBin(root) {
  const exe = process.platform === 'win32' ? 'python.exe' : 'python';
  const scripts = process.platform === 'win32' ? 'Scripts' : 'bin';
  return path.join(root, '.venv', scripts, exe);
}

function loadManifest() {
  const p = paths();
  const py = pythonBin(p.root);
  const script = path.join(p.root, 'scripts', 'setup', 'install_services.py');
  const r = spawnSync(py, [script, 'manifest'], { encoding: 'utf8' });
  if (r.status === 0 && r.stdout) {
    fs.mkdirSync(p.dir, { recursive: true });
    fs.writeFileSync(p.manifest, r.stdout);
    return JSON.parse(r.stdout);
  }
  if (fs.existsSync(p.manifest)) {
    return JSON.parse(fs.readFileSync(p.manifest, 'utf8'));
  }
  throw new Error(`could not obtain the service manifest (does ${py} exist?)`);
}

function runnableServices(manifest) {
  return manifest.services.filter((s) => {
    if (s.optional) return false;
    if (s.requires_claude_mem_plugin && !manifest.claude_mem_plugin_available) return false;
    // .sh scripts do not run on Windows native — skipped with a warning.
    if (process.platform === 'win32' && s.command[0].endsWith('.sh')) return false;
    return true;
  });
}

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function readPid(file) {
  try {
    return parseInt(fs.readFileSync(file, 'utf8').trim(), 10) || null;
  } catch {
    return null;
  }
}

function loadDotEnv(file) {
  const env = {};
  try {
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
      const m = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line.trim());
      if (m) env[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
    }
  } catch { /* .env is optional */ }
  return env;
}

function spawnService(svc, manifest, p) {
  const base = svc.env_file ? loadDotEnv(svc.env_file) : {};
  const env = { ...process.env, ...base, ...svc.env };
  const out = fs.openSync(p.logFile(svc.name), 'a');
  const child = spawn(svc.command[0], svc.command.slice(1), {
    cwd: manifest.root,
    env,
    detached: process.platform !== 'win32',
    windowsHide: true,
    stdio: ['ignore', out, out],
  });
  fs.writeFileSync(p.pidFile(svc.name), String(child.pid));
  return child;
}

// Daemon: runs in the foreground supervising; respawns with restart_sec.
function daemon() {
  const p = paths();
  const manifest = loadManifest();
  const children = new Map();
  let stopping = false;

  const log = (msg) =>
    fs.appendFileSync(p.daemonLog, `${new Date().toISOString()} ${msg}\n`);

  fs.mkdirSync(p.dir, { recursive: true });
  fs.writeFileSync(p.daemonPid, String(process.pid));

  const startOne = (svc) => {
    const child = spawnService(svc, manifest, p);
    children.set(svc.name, child);
    log(`start ${svc.name} pid=${child.pid}`);
    child.on('exit', (code) => {
      children.delete(svc.name);
      try { fs.unlinkSync(p.pidFile(svc.name)); } catch { /* already removed */ }
      if (stopping) return;
      if (svc.restart === 'always' || (svc.restart === 'on-failure' && code !== 0)) {
        log(`exit ${svc.name} code=${code} — restart in ${svc.restart_sec}s`);
        setTimeout(() => !stopping && startOne(svc), svc.restart_sec * 1000).unref?.();
      } else {
        log(`exit ${svc.name} code=${code} — no restart`);
      }
    });
  };

  const services = runnableServices(manifest);
  services.forEach(startOne);
  log(`supervisor active with ${services.length} service(s)`);

  const shutdown = () => {
    stopping = true;
    log('shutdown requested');
    for (const child of children.values()) {
      try { child.kill('SIGTERM'); } catch { /* already dead */ }
    }
    try { fs.unlinkSync(p.daemonPid); } catch { /* ok */ }
    setTimeout(() => process.exit(0), 2000);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
  setInterval(() => {}, 1 << 30); // keep the event loop alive
}

function start() {
  const p = paths();
  const existing = readPid(p.daemonPid);
  if (existing && pidAlive(existing)) {
    console.log(`supervisor already active (pid ${existing})`);
    return 0;
  }
  fs.mkdirSync(p.dir, { recursive: true });
  const out = fs.openSync(p.daemonLog, 'a');
  const child = spawn(process.execPath, [__filename, '__daemon'], {
    detached: true,
    windowsHide: true,
    stdio: ['ignore', out, out],
  });
  child.unref();
  console.log(`supervisor started (pid ${child.pid}); logs at ${p.daemonLog}`);
  return 0;
}

function stop() {
  const p = paths();
  const pid = readPid(p.daemonPid);
  if (!pid || !pidAlive(pid)) {
    console.log('supervisor is not running');
    return 0;
  }
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    process.kill(pid, 'SIGTERM');
  }
  console.log(`supervisor stopped (pid ${pid})`);
  return 0;
}

function status() {
  const p = paths();
  const manifest = loadManifest();
  const daemonPid = readPid(p.daemonPid);
  console.log(
    `supervisor: ${daemonPid && pidAlive(daemonPid) ? `active (pid ${daemonPid})` : 'stopped'}`
  );
  for (const svc of runnableServices(manifest)) {
    const pid = readPid(p.pidFile(svc.name));
    const state = pid && pidAlive(pid) ? `active (pid ${pid})` : 'stopped';
    console.log(`  ${svc.name.padEnd(28)} ${state}`);
  }
  return 0;
}

if (require.main === module && process.argv[2] === '__daemon') {
  daemon();
}

module.exports = { start, stop, status, loadManifest, runnableServices };
