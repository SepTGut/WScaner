const { exec } = require('child_process');
const path = require('path');
const config = require('./config');

function runOCR(filePath) {
  return new Promise((resolve, reject) => {
    const ocrScript = path.join(config.ROOT_DIR, 'ocr', 'ocr_processor.py');
    const gasParam = config.GAS_WEBHOOK_URL ? `--gas-url "${config.GAS_WEBHOOK_URL}"` : '';
    const cmd = `python "${ocrScript}" "${filePath}" ${gasParam}`;

    exec(cmd, { cwd: config.ROOT_DIR, maxBuffer: 15 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) {
        return reject(new Error(stderr || error.message));
      }
      try {
        const result = JSON.parse(stdout);
        resolve(result);
      } catch (err) {
        reject(new Error(`Failed to parse OCR output: ${stdout}`));
      }
    });
  });
}

module.exports = { runOCR };
