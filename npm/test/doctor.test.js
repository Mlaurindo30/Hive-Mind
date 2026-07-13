'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { requiredServiceHealth } = require('../lib/supervisor');

test('requiredServiceHealth ignores optional services and reports degraded required ones', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hive-doctor-'));
  const stateFile = path.join(root, 'state.json');
  const manifest = {
    root,
    claude_mem_plugin_available: true,
    services: [
      { name: 'api', required: true, enabled_profiles: ['local-min'], dependencies: [] },
      { name: 'dashboard', required: false, enabled_profiles: ['local-min'], dependencies: [] },
    ],
  };
  fs.writeFileSync(stateFile, JSON.stringify({
    api: { state: 'degraded' },
    dashboard: { state: 'healthy' },
  }));

  try {
    assert.deepEqual(requiredServiceHealth(manifest, 'local-min', stateFile), {
      healthy: false,
      missing: ['api'],
    });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
