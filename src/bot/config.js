const path = require('path');
const ROOT_DIR = path.join(__dirname, '..', '..');
require('dotenv').config({ path: path.join(ROOT_DIR, '.env') });

function normalizePhone(num) {
  if (!num) return '';
  let cleaned = num.replace(/[^0-9]/g, '');
  // Convert Indonesian 08xx to 628xx
  if (cleaned.startsWith('0')) {
    cleaned = '62' + cleaned.slice(1);
  }
  return cleaned;
}

module.exports = {
  ALLOWED_NUMBER: normalizePhone(process.env.ALLOWED_NUMBER || ''),
  START_COMMAND: (process.env.START_COMMAND || '#start').trim().toLowerCase(),
  STOP_COMMAND: (process.env.STOP_COMMAND || '#stop').trim().toLowerCase(),
  STATUS_COMMAND: (process.env.STATUS_COMMAND || '#status').trim().toLowerCase(),
  LOG_COMMAND: (process.env.LOG_COMMAND || '#log').trim().toLowerCase(),
  LINK_COMMAND: (process.env.LINK_COMMAND || '#link').trim().toLowerCase(),
  TUTO_COMMAND: (process.env.TUTO_COMMAND || '#tuto').trim().toLowerCase(),
  SPREADSHEET_URL: process.env.SPREADSHEET_URL || 'https://docs.google.com/spreadsheets/d/1fcBQJNoGU6bO1RcXEMiNCW5UB450VHmLTMtWPfDumFw/edit',
  GAS_WEBHOOK_URL: process.env.GAS_WEBHOOK_URL || '',
  GAS_SECRET_TOKEN: process.env.GAS_SECRET_TOKEN || '',
  AUTH_DIR: path.join(ROOT_DIR, 'runtime', 'auth'),
  TEMP_DIR: path.join(ROOT_DIR, 'runtime', 'temp'),
  LOGS_DIR: path.join(ROOT_DIR, 'runtime', 'logs'),
  GETDATA_DIR: path.join(ROOT_DIR, 'data', 'downloads'),
  OCR_DIR: path.join(ROOT_DIR, 'src', 'ocr'),
  DATA_DIR: path.join(ROOT_DIR, 'data'),
  ROOT_DIR: ROOT_DIR
};
