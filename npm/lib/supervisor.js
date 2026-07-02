'use strict';
// F3 — Supervisor multiplataforma: gerencia os serviços do manifesto
// (install_services.py manifest) como processos filhos com auto-restart.
// É o backend de serviços onde não há systemd/launchd (Windows nativo) e
// pode ser forçado em qualquer OS com HIVE_MIND_SUPERVISOR=1.
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
  throw new Error(`não consegui obter o manifesto de serviços (${py} existe?)`);
}

function runnableServices(manifest) {
  return manifest.services.filter((s) => {
    if (s.optional) return false;
    if (s.requires_claude_mem_plugin && !manifest.claude_mem_plugin_available) return false;
    // Scripts .sh não rodam em Windows nativo — pulados com aviso.
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
  } catch { /* .env opcional */ }
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

// Daemon: fica em foreground supervisionando; respawna com restart_sec.
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
      try { fs.unlinkSync(p.pidFile(svc.name)); } catch { /* já removido */ }
      if (stopping) return;
      if (svc.restart === 'always' || (svc.restart === 'on-failure' && code !== 0)) {
        log(`exit ${svc.name} code=${code} — restart em ${svc.restart_sec}s`);
        setTimeout(() => !stopping && startOne(svc), svc.restart_sec * 1000).unref?.();
      } else {
        log(`exit ${svc.name} code=${code} — sem restart`);
      }
    });
  };

  const services = runnableServices(manifest);
  services.forEach(startOne);
  log(`supervisor ativo com ${services.length} serviço(s)`);

  const shutdown = () => {
    stopping = true;
    log('shutdown solicitado');
    for (const child of children.values()) {
      try { child.kill('SIGTERM'); } catch { /* já morto */ }
    }
    try { fs.unlinkSync(p.daemonPid); } catch { /* ok */ }
    setTimeout(() => process.exit(0), 2000);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
  setInterval(() => {}, 1 << 30); // mantém o event loop vivo
}

function start() {
  const p = paths();
  const existing = readPid(p.daemonPid);
  if (existing && pidAlive(existing)) {
    console.log(`supervisor já ativo (pid ${existing})`);
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
  console.log(`supervisor iniciado (pid ${child.pid}); logs em ${p.daemonLog}`);
  return 0;
}

function stop() {
  const p = paths();
  const pid = readPid(p.daemonPid);
  if (!pid || !pidAlive(pid)) {
    console.log('supervisor não está rodando');
    return 0;
  }
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    process.kill(pid, 'SIGTERM');
  }
  console.log(`supervisor parado (pid ${pid})`);
  return 0;
}

function status() {
  const p = paths();
  const manifest = loadManifest();
  const daemonPid = readPid(p.daemonPid);
  console.log(
    `supervisor: ${daemonPid && pidAlive(daemonPid) ? `ativo (pid ${daemonPid})` : 'parado'}`
  );
  for (const svc of runnableServices(manifest)) {
    const pid = readPid(p.pidFile(svc.name));
    const state = pid && pidAlive(pid) ? `ativo (pid ${pid})` : 'parado';
    console.log(`  ${svc.name.padEnd(28)} ${state}`);
  }
  return 0;
}

if (require.main === module && process.argv[2] === '__daemon') {
  daemon();
}

module.exports = { start, stop, status, loadManifest, runnableServices };
