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

  // Seed from config.ALLOWED_NUMBER if file is empty and config has a number
  if (numbers.length === 0 && config.ALLOWED_NUMBER) {
    numbers = [config.ALLOWED_NUMBER];
    saveAllowedNumbers(numbers);
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

  return (sNorm && list.includes(sNorm)) || (rNorm && list.includes(rNorm));
}

module.exports = {
  normalizePhone,
  getAllowedNumbers,
  addNumber,
  removeNumber,
  isNumberAllowed
};
