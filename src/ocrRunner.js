const { exec } = require('child_process');
const path = require('path');
const config = require('./config');

function runOCR(filePath) {
  return new Promise((resolve, reject) => {
    const ocrScript = path.join(config.ROOT_DIR, 'ocr', 'ocr_processor.py');
    const gasParam = config.GAS_WEBHOOK_URL ? `--gas-url "${config.GAS_WEBHOOK_URL}"` : '';
    const cmd = `python "${ocrScript}" "${filePath}" ${gasParam}`;

    exec(cmd, { cwd: config.ROOT_DIR, maxBuffer: 15 * 1024 * 1024 }, (error, stdout, stderr) => {
      // First attempt: try finding JSON block even if python emitted deprecation/other warnings
      const rawOutput = (stdout || '').trim();
      const jsonMatch = rawOutput.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        try {
          const result = JSON.parse(jsonMatch[0]);
          return resolve(result);
        } catch (parseErr) {
          // If match fails parsing, continue to error handler
        }
      }

      if (error) {
        return reject(new Error(stderr || error.message || `OCR Process exited with error: ${rawOutput}`));
      }

      reject(new Error(`Failed to extract valid JSON from OCR output: ${rawOutput}`));
    });
  });
}

module.exports = { runOCR };
