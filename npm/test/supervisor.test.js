'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { selectServices, topologicalServices } = require('../lib/supervisor');

const manifest = {
  claude_mem_plugin_available: true,
  services: [
    { name: 'consumer', enabled_profiles: ['local-min'], dependencies: ['provider'], startup_order: 20 },
    { name: 'provider', enabled_profiles: ['local-min', 'local-full'], dependencies: [], startup_order: 10 },
    { name: 'full-only', enabled_profiles: ['local-full'], dependencies: [], startup_order: 5 },
  ],
};

test('selectServices respects the selected profile', () => {
  assert.deepEqual(selectServices(manifest, 'local-min').map((s) => s.name), ['consumer', 'provider']);
  assert.deepEqual(selectServices(manifest, 'local-full').map((s) => s.name), ['provider', 'full-only']);
});

test('topologicalServices starts dependencies before consumers', () => {
  const services = selectServices(manifest, 'local-min');
  assert.deepEqual(topologicalServices(services).map((s) => s.name), ['provider', 'consumer']);
});

test('topologicalServices rejects an undeclared dependency', () => {
  assert.throws(() => topologicalServices([{ name: 'api', dependencies: ['missing'], startup_order: 1 }]), /missing/);
});
test('waitForReadiness verifies an HTTP endpoint instead of a PID', async () => {
  const http = require('node:http');
  const { waitForReadiness } = require('../lib/supervisor');
  const server = http.createServer((_req, res) => { res.statusCode = 204; res.end(); });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  try {
    await assert.doesNotReject(waitForReadiness({
      readiness: { type: 'http', url: `http://127.0.0.1:${port}/health`, expected_status: [204], timeout_seconds: 1 },
    }));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('reported state does not promote a live PID to healthy', () => {
  const { reportedServiceState } = require('../lib/supervisor');
  assert.equal(reportedServiceState({ state: 'degraded', pid: 42 }, true), 'degraded');
  assert.equal(reportedServiceState(undefined, true), 'starting');
});

test('required services are reported when a capability excludes them', () => {
  const { requiredServiceErrors } = require('../lib/supervisor');
  const unavailable = { ...manifest, claude_mem_plugin_available: false, services: [
    { name: 'temporal', required: true, requires_claude_mem_plugin: true, enabled_profiles: ['local-min'], dependencies: [] },
  ] };
  assert.match(requiredServiceErrors(unavailable, 'local-min').join('\n'), /temporal/);
});

test('restart delay backs off and circuit breaker respects the configured limit', () => {
  const { restartDelayMs, canRestart } = require('../lib/supervisor');
  const svc = { restart_delay_seconds: 2, restart_max_delay_seconds: 10, restart_limit: 3 };
  assert.equal(restartDelayMs(svc, 0), 2000);
  assert.equal(restartDelayMs(svc, 3), 10000);
  assert.equal(canRestart(svc, 2), true);
  assert.equal(canRestart(svc, 3), false);
});

test('selectServices reads the persisted installation profile', () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hive-profile-'));
  fs.writeFileSync(path.join(root, '.env'), 'HIVE_MIND_PROFILE=local-full\n');
  try {
    assert.deepEqual(selectServices({ ...manifest, root }, undefined).map((s) => s.name), ['provider', 'full-only']);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('waitForRequiredHealthy blocks until every required manifest service is healthy', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const { waitForRequiredHealthy } = require('../lib/supervisor');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hive-required-health-'));
  const stateFile = path.join(root, 'state.json');
  const requiredManifest = {
    root,
    claude_mem_plugin_available: true,
    services: [{ name: 'milvus', required: true, enabled_profiles: ['local-full'], dependencies: [] }],
  };
  fs.writeFileSync(stateFile, JSON.stringify({ milvus: { state: 'starting' } }));

  try {
    setTimeout(() => fs.writeFileSync(stateFile, JSON.stringify({ milvus: { state: 'healthy' } })), 10);
    await assert.doesNotReject(waitForRequiredHealthy(requiredManifest, 'local-full', {
      stateFile,
      timeoutMs: 500,
      pollMs: 5,
    }));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
