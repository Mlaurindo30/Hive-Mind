'use strict';
// Thin Node wrapper over the native Hive-Mind daemon. It manages only the
// daemon process; the daemon owns service lifecycle, restart, health and state.
const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const { spawn, spawnSync } = require('child_process');
const { homeDir } = require('./platform');

function paths() {
  const root = homeDir();
  const dir = path.join(root, 'logs', 'supervisor');
  return {
    root,
    dir,
    manifest: path.join(dir, 'manifest.json'),
    daemonPid: path.join(dir, 'supervisor.pid'),
    startupLock: path.join(dir, 'supervisor.start.lock'),
    daemonLog: path.join(dir, 'supervisor.log'),
    managedState: path.join(root, '.hive-mind', 'state', 'services.managed.json'),
    shadowState: path.join(root, '.hive-mind', 'state', 'services.shadow.json'),
  };
}

function pythonBin(root) {
  const exe = process.platform === 'win32' ? 'python.exe' : 'python';
  const scripts = process.platform === 'win32' ? 'Scripts' : 'bin';
  return path.join(root, '.venv', scripts, exe);
}

function sh(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  return r.status ?? 1;
}

function readPid(file) {
  try {
    return parseInt(fs.readFileSync(file, 'utf8').trim(), 10) || null;
  } catch {
    return null;
  }
}

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function sleepMs(ms) {
  const duration = Math.max(1, ms | 0);
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, duration);
}

function loadManifest() {
  const p = paths();
  const py = pythonBin(p.root);
  const r = spawnSync(py, ['-m', 'hive_mind.cli', 'service', 'manifest', '--json'], {
    cwd: p.root,
    encoding: 'utf8',
  });
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

function selectedProfile(manifest, requested) {
  return requested || process.env.HIVE_MIND_PROFILE || loadDotEnv(path.join(manifest.root, '.env')).HIVE_MIND_PROFILE || 'local-min';
}

function selectServices(manifest, profile) {
  profile = selectedProfile(manifest, profile);
  let selected = manifest.services.filter((svc) => {
    const profiles = svc.enabled_profiles || ['local-min', 'local-full'];
    return profiles.includes(profile) && !(svc.requires_claude_mem_plugin && !manifest.claude_mem_plugin_available);
  });
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

function readState(stateFile) {
  if (stateFile) {
    try {
      return JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    } catch {
      return null;
    }
  }
  const p = paths();
  for (const candidate of [p.managedState, p.shadowState]) {
    if (!fs.existsSync(candidate)) continue;
    try {
      return JSON.parse(fs.readFileSync(candidate, 'utf8'));
    } catch {
      return null;
    }
  }
  return null;
}

function requiredServiceHealth(manifest, profile) {
  const unavailable = requiredServiceErrors(manifest, profile);
  if (unavailable.length) return { healthy: false, missing: unavailable };
  const state = readState();
  if (!state) {
    return {
      healthy: false,
      missing: runnableServices(manifest, profile)
        .filter((service) => service.required)
        .map((service) => service.name),
    };
  }
  const services = Array.isArray(state.services)
    ? state.services
    : Object.entries(state.services || {}).map(([name, payload]) => ({ name, ...payload }));
  const byName = new Map(services.map((svc) => [svc.name, svc]));
  const missing = runnableServices(manifest, profile)
    .filter((service) => service.required)
    .filter((service) => {
      const current = byName.get(service.name) || {};
      return current.readiness !== 'ready' && current.state !== 'running';
    })
    .map((service) => service.name);
  return { healthy: missing.length === 0, missing };
}

async function waitForRequiredHealthy(manifest, profile, options = {}) {
  const missingRequirements = requiredServiceErrors(manifest, profile);
  if (missingRequirements.length) throw new Error(missingRequirements.join('; '));

  const required = runnableServices(manifest, profile)
    .filter((service) => service.required)
    .map((service) => service.name);
  const timeoutMs = Math.max(1, options.timeoutMs ?? 300000);
  const pollMs = Math.max(1, options.pollMs ?? 250);
  const deadline = Date.now() + timeoutMs;
  let missing = required;

  do {
    const state = readState(options.stateFile) || {};
    const raw = state.services !== undefined ? state.services : state;
    const services = Array.isArray(raw)
      ? raw
      : Object.entries(raw).map(([name, payload]) => ({ name, ...payload }));
    const byName = new Map(services.map((svc) => [svc.name, svc]));
    missing = required.filter((name) => {
      const current = byName.get(name) || {};
      return (
        current.readiness !== 'ready' &&
        current.state !== 'running' &&
        current.state !== 'healthy'
      );
    });
    if (!missing.length) return;
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  } while (Date.now() < deadline);

  throw new Error(`required services are not healthy: ${missing.join(', ')}`);
}

function start() {
  const p = paths();
  fs.mkdirSync(p.dir, { recursive: true });
  let lockFd = null;
  for (;;) {
    try {
      lockFd = fs.openSync(p.startupLock, 'wx');
      fs.writeFileSync(lockFd, String(process.pid));
      break;
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const lockOwner = readPid(p.startupLock);
      if (lockOwner && pidAlive(lockOwner)) {
        console.log(`supervisor start already in progress (daemon pid ${lockOwner})`);
        return 0;
      }
      try { fs.unlinkSync(p.startupLock); } catch { /* stale lock */ }
    }
  }
  try {
    const existing = readPid(p.daemonPid);
    if (existing && pidAlive(existing)) {
      console.log(`daemon already active (pid ${existing})`);
      return 0;
    }
    const py = pythonBin(p.root);
    const out = fs.openSync(p.daemonLog, 'a');
    const child = spawn(py, ['-m', 'hive_mind.daemon.main', 'run', '--project-root', p.root, '--serve'], {
      cwd: p.root,
      detached: true,
      windowsHide: true,
      stdio: ['ignore', out, out],
    });
    child.unref();
    fs.writeFileSync(p.daemonPid, String(child.pid));
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
      if (pidAlive(child.pid)) break;
      sleepMs(50);
    }
    console.log(`daemon started (pid ${child.pid}); logs at ${p.daemonLog}`);
    return 0;
  } finally {
    try { if (lockFd !== null) fs.closeSync(lockFd); } catch {}
    try { fs.unlinkSync(p.startupLock); } catch {}
  }
}

function stop() {
  const p = paths();
  const pid = readPid(p.daemonPid);
  if (!pid || !pidAlive(pid)) {
    console.log('daemon is not running');
    try { fs.unlinkSync(p.daemonPid); } catch {}
    return 0;
  }
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    process.kill(pid, 'SIGTERM');
  }
  try { fs.unlinkSync(p.daemonPid); } catch {}
  console.log(`daemon stopped (pid ${pid})`);
  return 0;
}

function status() {
  const p = paths();
  const py = pythonBin(p.root);
  const health = sh(py, ['-m', 'hive_mind.cli', 'service', 'status', '--project-root', p.root]);
  const ping = spawnSync(py, ['-m', 'hive_mind.cli', 'service', 'ping', '--project-root', p.root], {
    cwd: p.root,
    encoding: 'utf8',
  });
  if (ping.status !== 0 && ping.stderr) {
    process.stderr.write(ping.stderr);
  }
  return health === 0 && ping.status === 0 ? 0 : 1;
}

function waitForReadiness(service, options = {}) {
  const readiness = (service && service.readiness) || {};
  if (readiness.type !== 'http') {
    return Promise.reject(new Error(`unsupported readiness type: ${readiness.type}`));
  }
  const expected = readiness.expected_status || [200];
  const timeoutMs = (readiness.timeout_seconds || 5) * 1000;
  const client = String(readiness.url).startsWith('https') ? https : http;
  return new Promise((resolve, reject) => {
    const req = client.get(readiness.url, { timeout: timeoutMs }, (res) => {
      res.resume();
      if (expected.includes(res.statusCode)) resolve(true);
      else reject(new Error(`readiness returned ${res.statusCode}`));
    });
    req.on('timeout', () => req.destroy(new Error('readiness timeout')));
    req.on('error', reject);
  });
}

function shouldAdoptExistingService(service, healthy) {
  if (!healthy) return false;
  if (service && service.external) return false;
  if (service && service.healthcheck && service.healthcheck.type === 'none') return false;
  return true;
}

function reportedServiceState(serviceState, pidAlive) {
  return (serviceState && serviceState.state) || 'starting';
}

function healthStateTransition(current, healthy) {
  const cur = current || {};
  const extra = {};
  if (cur.pid !== undefined) extra.pid = cur.pid;
  if (cur.restart_count !== undefined) extra.restart_count = cur.restart_count;
  if (healthy) return { state: 'healthy', extra };
  extra.last_error = 'healthcheck failed';
  return { state: 'degraded', extra };
}

function restartDelayMs(service, restartCount) {
  const base = (service && service.restart_delay_seconds) || 1;
  const max = (service && service.restart_max_delay_seconds) || base;
  return Math.min(base * Math.pow(2, restartCount), max) * 1000;
}

function canRestart(service, restartCount) {
  const limit = service && service.restart_limit;
  if (limit === undefined || limit === null) return true;
  return restartCount < limit;
}

module.exports = {
  start,
  stop,
  status,
  loadManifest,
  runnableServices,
  selectServices,
  selectedProfile,
  topologicalServices,
  requiredServiceErrors,
  requiredServiceHealth,
  waitForRequiredHealthy,
  waitForReadiness,
  shouldAdoptExistingService,
  reportedServiceState,
  healthStateTransition,
  restartDelayMs,
  canRestart,
};
