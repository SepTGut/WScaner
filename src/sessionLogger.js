const fs = require('fs');
const path = require('path');
const config = require('./config');

const MAX_LOG_FILES = 10;
let currentLogFile = null;

function ensureLogsDir() {
  if (!fs.existsSync(config.LOGS_DIR)) {
    fs.mkdirSync(config.LOGS_DIR, { recursive: true });
  }
}

function cleanOldLogs(maxFiles = MAX_LOG_FILES) {
  try {
    ensureLogsDir();
    const files = fs.readdirSync(config.LOGS_DIR)
      .filter(f => f.endsWith('.log'))
      .map(f => {
        const fullPath = path.join(config.LOGS_DIR, f);
        return {
          name: f,
          path: fullPath,
          time: fs.statSync(fullPath).mtimeMs
        };
      })
      .sort((a, b) => a.time - b.time); // Oldest first

    while (files.length > maxFiles) {
      const oldest = files.shift();
      try {
        fs.unlinkSync(oldest.path);
        console.log(`🗑️ [LOG] Menghapus log lama: ${oldest.name}`);
      } catch (e) {
        console.error(`Gagal menghapus log lama ${oldest.name}:`, e.message);
      }
    }
  } catch (err) {
    console.error('Error saat membersihkan log lama:', err.message);
  }
}

function startSession() {
  ensureLogsDir();
  cleanOldLogs(MAX_LOG_FILES - 1); // Make room for new file

  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const dateStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
  
  const fileName = `session_${dateStr}.log`;
  currentLogFile = path.join(config.LOGS_DIR, fileName);

  const header = `======================================================\n` +
    `  WScaner - WhatsApp OCR Scanner Session Log\n` +
    `  Waktu Mulai : ${now.toLocaleString('id-ID')}\n` +
    `======================================================\n\n`;

  fs.writeFileSync(currentLogFile, header, 'utf-8');
  console.log(`📁 [LOG] Sesi baru dimulai. File log: ${fileName}`);
  return currentLogFile;
}

function logToSession(text) {
  if (!currentLogFile) {
    // If not started yet, automatically start a session
    startSession();
  }
  const timestamp = new Date().toLocaleTimeString('id-ID');
  const line = `[${timestamp}] ${text}\n`;
  try {
    fs.appendFileSync(currentLogFile, line, 'utf-8');
  } catch (err) {
    console.error('Gagal menulis ke file log sesi:', err.message);
  }
}

function endSession() {
  if (currentLogFile && fs.existsSync(currentLogFile)) {
    const footer = `\n======================================================\n` +
      `  Waktu Berhenti: ${new Date().toLocaleString('id-ID')}\n` +
      `======================================================\n`;
    try {
      fs.appendFileSync(currentLogFile, footer, 'utf-8');
    } catch (e) {}
  }
  const finishedFile = currentLogFile;
  currentLogFile = null;
  cleanOldLogs(MAX_LOG_FILES);
  return finishedFile;
}

function getLatestLogFile() {
  ensureLogsDir();
  if (currentLogFile && fs.existsSync(currentLogFile)) {
    return currentLogFile;
  }
  const files = fs.readdirSync(config.LOGS_DIR)
    .filter(f => f.endsWith('.log'))
    .map(f => {
      const fullPath = path.join(config.LOGS_DIR, f);
      return { path: fullPath, time: fs.statSync(fullPath).mtimeMs };
    })
    .sort((a, b) => b.time - a.time); // Newest first

  return files.length > 0 ? files[0].path : null;
}

module.exports = {
  startSession,
  logToSession,
  endSession,
  getLatestLogFile,
  cleanOldLogs
};
