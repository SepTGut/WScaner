const fs = require('fs');
const path = require('path');
const config = require('./config');

const NUMBERS_FILE = path.join(config.ROOT_DIR, 'allowed_numbers.json');

function normalizePhone(num) {
  if (!num) return '';
  let cleaned = String(num).replace(/[^0-9]/g, '');
  // Convert Indonesian 08xx to 628xx
  if (cleaned.startsWith('0')) {
    cleaned = '62' + cleaned.slice(1);
  }
  return cleaned;
}

function loadAllowedNumbers() {
  let numbers = [];
  try {
    if (fs.existsSync(NUMBERS_FILE)) {
      const content = fs.readFileSync(NUMBERS_FILE, 'utf-8');
      const data = JSON.parse(content);
      if (Array.isArray(data)) {
        numbers = data.map(normalizePhone).filter(Boolean);
      }
    }
  } catch (err) {
    console.error('Gagal membaca allowed_numbers.json:', err.message);
  }

  // Also include config.ALLOWED_NUMBER if defined in .env
  if (config.ALLOWED_NUMBER && !numbers.includes(config.ALLOWED_NUMBER)) {
    numbers.push(config.ALLOWED_NUMBER);
  }

  return [...new Set(numbers)];
}

function saveAllowedNumbers(numbers) {
  try {
    const cleanList = [...new Set(numbers.map(normalizePhone).filter(Boolean))];
    fs.writeFileSync(NUMBERS_FILE, JSON.stringify(cleanList, null, 2), 'utf-8');
    return true;
  } catch (err) {
    console.error('Gagal menyimpan allowed_numbers.json:', err.message);
    return false;
  }
}

function getAllowedNumbers() {
  return loadAllowedNumbers();
}

function resolveLidToPhone(identifier) {
  if (!identifier) return '';
  const clean = String(identifier).replace(/[^0-9]/g, '');
  if (!clean) return '';

  // 1. Direct match in allowed list
  const list = loadAllowedNumbers();
  const norm = normalizePhone(clean);
  if (list.includes(norm)) return norm;

  // 2. Check auth_info for reverse LID mapping: lid-mapping-<clean>_reverse.json
  try {
    const reverseFile = path.join(config.AUTH_DIR, `lid-mapping-${clean}_reverse.json`);
    if (fs.existsSync(reverseFile)) {
      const content = fs.readFileSync(reverseFile, 'utf-8');
      const mapped = JSON.parse(content);
      if (mapped) {
        return normalizePhone(mapped);
      }
    }
  } catch (e) {}

  return norm;
}

function resolvePhoneToLid(rawPhone) {
  const norm = normalizePhone(rawPhone);
  if (!norm) return '';
  try {
    const forwardFile = path.join(config.AUTH_DIR, `lid-mapping-${norm}.json`);
    if (fs.existsSync(forwardFile)) {
      const content = fs.readFileSync(forwardFile, 'utf-8');
      const mapped = JSON.parse(content);
      if (mapped) return String(mapped);
    }

    // Fallback: search reverse LID files in auth_info
    if (fs.existsSync(config.AUTH_DIR)) {
      const files = fs.readdirSync(config.AUTH_DIR);
      for (const f of files) {
        if (f.startsWith('lid-mapping-') && f.endsWith('_reverse.json')) {
          const fullPath = path.join(config.AUTH_DIR, f);
          const content = fs.readFileSync(fullPath, 'utf-8');
          if (content.includes(norm)) {
            try {
              const mapped = JSON.parse(content);
              if (normalizePhone(mapped) === norm) {
                const lid = f.replace('lid-mapping-', '').replace('_reverse.json', '');
                return lid;
              }
            } catch (e) {}
          }
        }
      }
    }
  } catch (e) {}
  return '';
}

function addNumber(rawPhone) {
  const norm = normalizePhone(rawPhone);
  if (!norm || norm.length < 9 || norm.length > 16) {
    return {
      success: false,
      error: 'Format nomor tidak valid. Minimal 9 digit angka (contoh: +62 812 3456 7890).'
    };
  }

  const list = loadAllowedNumbers();
  if (list.includes(norm)) {
    return {
      success: false,
      error: `Nomor *+${norm}* sudah ada dalam daftar izin.`,
      numbers: list
    };
  }

  list.push(norm);
  saveAllowedNumbers(list);
  console.log(`➕ [AKSES] Nomor +${norm} ditambahkan ke daftar izin.`);
  return {
    success: true,
    number: norm,
    numbers: list
  };
}

function removeNumber(rawPhone) {
  const norm = normalizePhone(rawPhone);
  if (!norm) {
    return {
      success: false,
      error: 'Format nomor tidak valid.'
    };
  }

  const list = loadAllowedNumbers();
  const idx = list.indexOf(norm);
  if (idx === -1) {
    return {
      success: false,
      error: `Nomor *+${norm}* tidak ditemukan dalam daftar izin.`,
      numbers: list
    };
  }

  list.splice(idx, 1);
  saveAllowedNumbers(list);
  console.log(`➖ [AKSES] Nomor +${norm} dihapus dari daftar izin.`);
  return {
    success: true,
    number: norm,
    numbers: list
  };
}

function isNumberAllowed(senderNumber, remoteNumber) {
  const list = loadAllowedNumbers();
  if (list.length === 0) return false;

  const sNorm = normalizePhone(senderNumber);
  const rNorm = normalizePhone(remoteNumber);

  // 1. Direct match with stored numbers
  if ((sNorm && list.includes(sNorm)) || (rNorm && list.includes(rNorm))) {
    return true;
  }

  // 2. Resolve sender/remote if they are WhatsApp LIDs (e.g. @lid)
  const sResolved = resolveLidToPhone(senderNumber);
  if (sResolved && list.includes(sResolved)) {
    return true;
  }

  const rResolved = resolveLidToPhone(remoteNumber);
  if (rResolved && list.includes(rResolved)) {
    return true;
  }

  // 3. Match against LIDs of any allowed numbers
  for (const allowedNum of list) {
    const lid = resolvePhoneToLid(allowedNum);
    if (lid && (lid === senderNumber || lid === remoteNumber || lid === sNorm || lid === rNorm)) {
      return true;
    }
  }

  return false;
}

module.exports = {
  normalizePhone,
  getAllowedNumbers,
  addNumber,
  removeNumber,
  isNumberAllowed,
  resolveLidToPhone,
  resolvePhoneToLid
};

