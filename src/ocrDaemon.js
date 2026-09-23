const { spawn } = require('child_process');
const path = require('path');
const axios = require('axios');
const config = require('./config');

const OCR_PORT = process.env.OCR_PORT || 5005;
const OCR_HOST = '127.0.0.1';
const SERVER_URL = `http://${OCR_HOST}:${OCR_PORT}`;

let daemonProcess = null;
let isStarted = false;

async function checkHealth() {
  try {
    const res = await axios.get(`${SERVER_URL}/health`, { timeout: 1000 });
    return res.data && res.data.status === 'ok';
  } catch (err) {
    return false;
  }
}

async function start() {
  if (isStarted) {
    const alive = await checkHealth();
    if (alive) return true;
  }

  // First, check if an existing daemon is already running (e.g. from previous run)
  const alreadyRunning = await checkHealth();
  if (alreadyRunning) {
    console.log(`⚡ [OCR DAEMON] Worker Python sudah aktif di ${SERVER_URL}`);
    isStarted = true;
    return true;
  }

  console.log(`🚀 [OCR DAEMON] Memulai background worker Python di ${SERVER_URL}...`);
  const serverScript = path.join(config.ROOT_DIR, 'ocr', 'server.py');

  const pythonCmd = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
  daemonProcess = spawn(pythonCmd, [serverScript], {
    cwd: config.ROOT_DIR,
    env: { ...process.env, OCR_PORT: String(OCR_PORT) },
    stdio: ['ignore', 'pipe', 'pipe']
  });

  daemonProcess.on('error', (err) => {
    console.warn(`⚠️ [OCR DAEMON] Gagal menjalankan Python daemon (${err.message}). Beralih ke mode CLI.`);
    isStarted = false;
    daemonProcess = null;
  });

  daemonProcess.stdout.on('data', (data) => {
    const str = data.toString().trim();
    if (str) console.log(`[OCR WORKER] ${str}`);
  });

  daemonProcess.stderr.on('data', (data) => {
    const str = data.toString().trim();
    if (str && !str.includes('DeprecationWarning')) {
      console.error(`[OCR WORKER ERR] ${str}`);
    }
  });

  daemonProcess.on('close', (code) => {
    console.log(`⚠️ [OCR DAEMON] Worker Python berhenti (exit code: ${code})`);
    isStarted = false;
    daemonProcess = null;
  });

  // Wait for server to become healthy (up to 15 seconds)
  const maxAttempts = 50;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 300));
    if (await checkHealth()) {
      console.log(`✅ [OCR DAEMON] Worker Python siap melayani request OCR instan!`);
      isStarted = true;
      return true;
    }
  }

  console.warn(`⚠️ [OCR DAEMON] Worker Python belum merespons, bot akan menggunakan fallback CLI.`);
  return false;
}

async function stop() {
  if (!isStarted && !daemonProcess) return;

  try {
    await axios.post(`${SERVER_URL}/shutdown`, {}, { timeout: 1000 });
  } catch (e) {
    // Ignore error if already dead
  }

  if (daemonProcess) {
    try {
      daemonProcess.kill('SIGTERM');
    } catch (e) {}
    daemonProcess = null;
  }
  isStarted = false;
}

// Clean up child process when Node process exits
process.on('exit', () => {
  if (daemonProcess) {
    try { daemonProcess.kill(); } catch (e) {}
  }
});
process.on('SIGINT', () => {
  stop().then(() => process.exit(0));
});
process.on('SIGTERM', () => {
  stop().then(() => process.exit(0));
});

module.exports = {
  start,
  stop,
  checkHealth,
  SERVER_URL
};
