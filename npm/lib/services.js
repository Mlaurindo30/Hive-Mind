'use strict';
// Service abstraction per platform: systemd (Linux/WSL), launchd (macOS),
// Node supervisor (Windows native or HIVE_MIND_SUPERVISOR=1).
const { spawnSync } = require('child_process');
const supervisor = require('./supervisor');
const { homeDir } = require('./platform');

function backend() {
  if (process.env.HIVE_MIND_SUPERVISOR === '1') return 'supervisor';
  if (process.platform === 'win32') return 'supervisor';
  if (process.platform === 'darwin') return 'launchd';
  return 'systemd';
}

function sh(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'inherit' });
  return r.status ?? 1;
}

function managedUnits() {
  const manifest = supervisor.loadManifest();
  return supervisor.runnableServices(manifest).map((service) => `${service.name}.service`);
}

function systemd(action) {
  const units = managedUnits();
  if (action === 'status') {
    if (!units.length) {
      console.log('no managed Hive-Mind systemd units in manifest');
      return 0;
    }
    return sh('systemctl', ['--user', 'list-units', ...units, '--no-pager']);
  }
  if (!units.length) {
    console.log('no managed Hive-Mind systemd units in manifest');
    return 0;
  }
  return sh('systemctl', ['--user', action, ...units]);
}

function launchd(action) {
  const labels = managedUnits().map(
    (u) => `com.hivemind.${u.replace('.service', '')}`
  );
  if (action === 'status') {
    return sh('bash', ['-c', `launchctl list | grep -E 'com.hivemind' || echo 'no active com.hivemind LaunchAgent'`]);
  }
  const verb = action === 'stop' ? 'unload' : 'load';
  let code = 0;
  for (const label of labels) {
    const plist = `${process.env.HOME}/Library/LaunchAgents/${label}.plist`;
    code = sh('bash', ['-c', `[ -f '${plist}' ] && launchctl ${verb} '${plist}' || true`]) || code;
  }
  return code;
}

function dispatch(action) {
  const b = backend();
  if (b === 'supervisor') {
    if (action === 'start' || action === 'restart') {
      if (action === 'restart') supervisor.stop();
      return supervisor.start();
    }
    if (action === 'stop') return supervisor.stop();
    if (action === 'wait') {
      return supervisor.waitForRequiredHealthy(supervisor.loadManifest())
        .then(() => { console.log('required services are healthy'); return 0; })
        .catch((error) => { console.error(error.message); return 1; });
    }
    return supervisor.status();
  }
  if (b === 'launchd') {
    if (action === 'restart') { launchd('stop'); return launchd('start'); }
    return launchd(action);
  }
  return systemd(action === 'start' ? 'restart' : action);
}

module.exports = { dispatch, backend, homeDir, managedUnits };
