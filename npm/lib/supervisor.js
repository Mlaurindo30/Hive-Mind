'use strict';
// F3 — Cross-platform supervisor: manages services from the manifest
// (install_services.py manifest) as child processes with auto-restart.
// It is the service backend where systemd/launchd is unavailable (Windows native)
// and can be forced on any OS with HIVE_MIND_SUPERVISOR=1.
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const http = require('http');
const https = require('https');
const net = require('net');
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
    stateFile: path.join(dir, 'state.json'),
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

function selectedProfile(manifest, requested) {
  return requested || process.env.HIVE_MIND_PROFILE || loadDotEnv(path.join(manifest.root, ".env")).HIVE_MIND_PROFILE || "local-min";
}
function selectServices(manifest, profile) {
  profile = selectedProfile(manifest, profile);
  let selected = manifest.services.filter((svc) => {
    const profiles = svc.enabled_profiles || ["local-min", "local-full"];
    return profiles.includes(profile) && !(svc.requires_claude_mem_plugin && !manifest.claude_mem_plugin_available);
  });
  // A consumer is never runnable when its provider was excluded by the profile
  // or by a missing runtime capability (for example claude-mem).
  for (;;) {
    const names = new Set(selected.map((svc) => svc.name));
    const next = selected.filter((svc) => (svc.dependencies || []).every((dependency) => names.has(dependency)));
    if (next.length === selected.length) return next;
    selected = next;
  }
}

function requiredServiceErrors(manifest, profile) {
  profile = selectedProfile(manifest, profile);
  const inProfile = manifest.services.filter((svc) => (svc.enabled_profiles || ['local-min', 'local-full']).includes(profile));
  const runnable = new Set(selectServices(manifest, profile).map((svc) => svc.name));
  return inProfile.filter((svc) => svc.required && !runnable.has(svc.name)).map((svc) => {
    if (svc.requires_claude_mem_plugin && !manifest.claude_mem_plugin_available) {
      return 'required service ' + svc.name + ' requires the claude-mem plugin';
    }
    return 'required service ' + svc.name + ' has an unavailable dependency';
  });
}
function topologicalServices(services) {
  const byName = new Map(services.map((svc) => [svc.name, svc]));
  const visiting = new Set();
  const visited = new Set();
  const ordered = [];
  const visit = (svc) => {
    if (visited.has(svc.name)) return;
    if (visiting.has(svc.name)) throw new Error(`service dependency cycle at ${svc.name}`);
    visiting.add(svc.name);
    for (const dependency of svc.dependencies || []) {
      const provider = byName.get(dependency);
      if (!provider) throw new Error(`service ${svc.name} requires unavailable dependency ${dependency}`);
      visit(provider);
    }
    visiting.delete(svc.name);
    visited.add(svc.name);
    ordered.push(svc);
  };
  [...services].sort((a, b) => (a.startup_order || 0) - (b.startup_order || 0)).forEach(visit);
  return ordered;
}
function runnableServices(manifest, profile) {
  return topologicalServices(selectServices(manifest, profile));
}

function restartDelayMs(service, attempt) {
  const base = Math.max(1, service.restart_delay_seconds || service.restart_sec || 5);
  const maximum = Math.max(base, service.restart_max_delay_seconds || 120);
  return Math.min(maximum, base * (2 ** attempt)) * 1000;
}

function canRestart(service, attempts) {
  return attempts < Math.max(0, service.restart_limit ?? 10);
}
function probeReadiness(check) {
  if (!check || check.type === "none") return Promise.resolve(true);
  const timeoutMs = Math.max(100, (check.timeout_seconds || 10) * 1000);
  if (check.type === "tcp") return new Promise((resolve) => {
    const socket = net.connect(check.port, check.host || "127.0.0.1");
    const done = (ok) => { socket.destroy(); resolve(ok); };
    socket.setTimeout(timeoutMs, () => done(false));
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
  });
  if (check.type === "command") return new Promise((resolve) => {
    const command = check.command || [];
    if (!command.length) return resolve(false);
    const child = spawn(command[0], command.slice(1), { windowsHide: true, stdio: 'ignore' });
    const timer = setTimeout(() => { try { child.kill(); } catch {} resolve(false); }, timeoutMs);
    child.once('error', () => { clearTimeout(timer); resolve(false); });
    child.once('exit', (code) => { clearTimeout(timer); resolve(code === 0); });
  });
  if (check.type === "http") return new Promise((resolve) => {
    const client = String(check.url).startsWith("https:") ? https : http;
    const request = client.get(check.url, { timeout: timeoutMs }, (response) => {
      response.resume();
      resolve((check.expected_status || [200]).includes(response.statusCode));
    });
    request.once("timeout", () => request.destroy());
    request.once("error", () => resolve(false));
  });
  return Promise.resolve(false);
}

async function waitForReadiness(service) {
  const check = service.readiness || { type: "none" };
  if (check.type === "none") return;
  const deadline = Date.now() + Math.max(1, check.timeout_seconds || 60) * 1000;
  do {
    if (await probeReadiness(check)) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  } while (Date.now() < deadline);
  throw new Error(`readiness timeout for ${service.name || "service"}`);
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

function platformCommand(service) {
  const platform = process.platform === 'win32' ? 'windows'
    : (process.platform === 'darwin' ? 'darwin' : 'linux');
  return service.commands?.[platform] || service.command;
}
function spawnService(svc, manifest, p) {
  const base = svc.env_file ? loadDotEnv(svc.env_file) : {};
  const env = { ...process.env, ...base, ...svc.env };
  const out = fs.openSync(p.logFile(svc.name), 'a');
  const command = platformCommand(svc);
  const child = spawn(command[0], command.slice(1), {
    cwd: svc.working_directory || manifest.root,
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
  const states = {};
  const restartAttempts = new Map();

  const log = (msg) =>
    fs.appendFileSync(p.daemonLog, `${new Date().toISOString()} ${msg}\n`);

  fs.mkdirSync(p.dir, { recursive: true });
  fs.writeFileSync(p.daemonPid, String(process.pid));
  const setState = (svc, state, extra = {}) => {
    states[svc.name] = { state, updated_at: new Date().toISOString(), ...extra };
    fs.writeFileSync(p.stateFile, JSON.stringify(states, null, 2));
  };

  const startOne = async (svc) => {
    if (svc.external) {
      setState(svc, "starting");
      try {
        await waitForReadiness(svc);
        setState(svc, "healthy");
        log("external ready " + svc.name);
      } catch (error) {
        setState(svc, "degraded", { last_error: error.message });
        log("external degraded " + svc.name + ": " + error.message);
        return;
      }
      return;
    }
    const child = spawnService(svc, manifest, p);
    children.set(svc.name, child);
    setState(svc, "starting", { pid: child.pid });
    log(`start ${svc.name} pid=${child.pid}`);
    child.on('exit', (code) => {
      children.delete(svc.name);
      setState(svc, "stopped", { exit_code: code });
      try { fs.unlinkSync(p.pidFile(svc.name)); } catch { /* already removed */ }
      if (stopping) return;
      if (svc.restart === 'always' || (svc.restart === 'on-failure' && code !== 0)) {
        const attempts = restartAttempts.get(svc.name) || 0;
        if (!canRestart(svc, attempts)) {
          setState(svc, "failed", { exit_code: code, last_error: "restart limit reached" });
          log(`circuit-open ${svc.name} after ${attempts} restart attempts`);
          return;
        }
        restartAttempts.set(svc.name, attempts + 1);
        const delay = restartDelayMs(svc, attempts);
        log(`exit ${svc.name} code=${code} — restart in ${delay}ms`);
        setTimeout(() => !stopping && startOne(svc), delay).unref?.();
      } else {
        log(`exit ${svc.name} code=${code} — no restart`);
      }
    });
    try {
      await waitForReadiness(svc);
      setState(svc, "healthy", { pid: child.pid });
      log(`ready ${svc.name} pid=${child.pid}`);
    } catch (error) {
      setState(svc, "degraded", { pid: child.pid, last_error: error.message });
      log(`degraded ${svc.name}: ${error.message}`);
      return;
    }
  };

  const requiredErrors = requiredServiceErrors(manifest);
  if (requiredErrors.length) throw new Error(requiredErrors.join('; '));
  const services = runnableServices(manifest);
  (async () => {
    for (const service of services) await startOne(service);
    log(`supervisor active with ${services.length} service(s)`);
  })().catch((error) => log(`supervisor startup failed: ${error.message}`));

  const healthTimer = setInterval(async () => {
    for (const service of services) {
      const check = service.healthcheck || service.readiness;
      if (!check || check.type === "none") continue;
      const ok = await probeReadiness(check);
      if (!ok) {
        const current = states[service.name] || {};
        setState(service, "degraded", { ...current, last_error: "healthcheck failed" });
        log("healthcheck failed " + service.name);
      }
    }
  }, 15000);
  healthTimer.unref?.();
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

function reportedServiceState(record, pidIsAlive) {
  if (record && record.state) return record.state;
  return pidIsAlive ? 'starting' : 'stopped';
}

function loadState(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return {}; }
}
function status() {
  const p = paths();
  const manifest = loadManifest();
  const daemonPid = readPid(p.daemonPid);
  const states = loadState(p.stateFile);
  console.log(
    `supervisor: ${daemonPid && pidAlive(daemonPid) ? `active (pid ${daemonPid})` : 'stopped'}`
  );
  for (const svc of runnableServices(manifest)) {
    const pid = readPid(p.pidFile(svc.name));
    const alive = Boolean(pid && pidAlive(pid));
    const state = reportedServiceState(states[svc.name], alive);
    if (!alive && pid) { try { fs.unlinkSync(p.pidFile(svc.name)); } catch {} }
    console.log(`  ${svc.name.padEnd(28)} ${state}${alive ? ` (pid ${pid})` : ''}`);
  }
  return 0;
}

if (require.main === module && process.argv[2] === '__daemon') {
  daemon();
}

module.exports = { start, stop, status, loadManifest, runnableServices, selectServices, selectedProfile, topologicalServices, requiredServiceErrors, probeReadiness, waitForReadiness, platformCommand, reportedServiceState, restartDelayMs, canRestart };
