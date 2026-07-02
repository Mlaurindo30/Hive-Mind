'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

function isWSL() {
  if (process.platform !== 'linux') return false;
  try {
    return /microsoft/i.test(fs.readFileSync('/proc/version', 'utf8'));
  } catch {
    return false;
  }
}

function wslAvailableFromWindows() {
  if (process.platform !== 'win32') return false;
  try {
    execFileSync('wsl.exe', ['--status'], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function homeDir() {
  return process.env.HIVE_MIND_HOME || path.join(os.homedir(), 'Hive-Mind');
}

function which(cmd) {
  const exts = process.platform === 'win32' ? ['.exe', '.cmd', '.bat', ''] : [''];
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    for (const ext of exts) {
      const candidate = path.join(dir, cmd + ext);
      try {
        fs.accessSync(candidate, fs.constants.X_OK);
        return candidate;
      } catch { /* continua */ }
    }
  }
  return null;
}

module.exports = { isWSL, wslAvailableFromWindows, homeDir, which };
