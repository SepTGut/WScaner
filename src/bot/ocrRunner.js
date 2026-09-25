const { execFile } = require('child_process');
const path = require('path');
const axios = require('axios');
const config = require('./config');
const ocrDaemon = require('./ocrDaemon');

async function runOCRViaDaemon(filePath) {
  const engine = process.env.OCR_ENGINE || 'windows';
  const res = await axios.post(`${ocrDaemon.SERVER_URL}/ocr`, {
    image_path: path.resolve(filePath),
    include_drive_image: true,
    engine: engine
  }, { timeout: 45000 });
  return res.data;
}

function runOCRViaCLI(filePath) {
  return new Promise((resolve, reject) => {
    const ocrScript = path.join(config.ROOT_DIR, 'src', 'ocr', 'ocr_processor.py');
    const pythonCmd = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
    const args = [ocrScript, path.resolve(filePath), '--no-gas', '--keep-b64'];
    if (process.env.OCR_ENGINE) {
      args.push('--engine', process.env.OCR_ENGINE);
    }

    execFile(pythonCmd, args, { cwd: config.ROOT_DIR, maxBuffer: 30 * 1024 * 1024 }, (error, stdout, stderr) => {
      const rawOutput = (stdout || '').trim();
      const jsonMatch = rawOutput.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        try {
          const result = JSON.parse(jsonMatch[0]);
          return resolve(result);
        } catch (parseErr) {
          // Continue to error handler
        }
      }

      if (error) {
        return reject(new Error(stderr || error.message || `OCR Process exited with error: ${rawOutput}`));
      }

      reject(new Error(`Failed to extract valid JSON from OCR output: ${rawOutput}`));
    });
  });
}

/**
 * Fast OCR Runner:
 * 1. Tries local persistent Python daemon (latensi ~300-500ms).
 * 2. Falls back to CLI execution if daemon is inactive.
 */
async function runOCR(filePath) {
  try {
    return await runOCRViaDaemon(filePath);
  } catch (daemonErr) {
    console.warn(`[OCR RUNNER] Daemon tidak merespons (${daemonErr.message}), beralih ke CLI fallback...`);
    return await runOCRViaCLI(filePath);
  }
}

/**
 * Asynchronous sync to Google Apps Script (Drive + Sheet).
 * Non-blocking, executes in background.
 */
async function syncToGAS(payload, maxRetries = 2) {
  if (!config.GAS_WEBHOOK_URL || !config.GAS_WEBHOOK_URL.trim()) {
    return { status: 'skipped', message: 'No GAS URL configured' };
  }

  const cleanUrl = config.GAS_WEBHOOK_URL.trim();
  let lastErr = null;
  const fullPayload = config.GAS_SECRET_TOKEN
    ? { ...payload, secret: config.GAS_SECRET_TOKEN }
    : payload;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const resp = await axios.post(cleanUrl, fullPayload, {
        timeout: 45000,
        maxRedirects: 5,
        headers: { 'Content-Type': 'application/json' }
      });

      if (typeof resp.data === 'string' && (resp.data.includes('<html') || resp.data.includes('<!DOCTYPE'))) {
        return {
          status: 'error',
          http_code: 403,
          message: 'Google memerlukan izin akses Web App (Pastikan disetel ke Anyone/Siapa Saja)'
        };
      }

      const data = typeof resp.data === 'object' ? resp.data : { raw: resp.data };
      data.http_code = resp.status;
      return data;
    } catch (err) {
      lastErr = err;
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, 1500 * attempt));
      }
    }
  }

  return {
    status: 'error',
    message: lastErr ? lastErr.message : 'Max retries exceeded'
  };
}

module.exports = { runOCR, syncToGAS };
