const { downloadMediaMessage, jidNormalizedUser } = require('@whiskeysockets/baileys');
const fs = require('fs');
const path = require('path');
let convertHeic = null;
try {
  convertHeic = require('heic-convert');
} catch (e) {}
const config = require('./config');
const { runOCR, syncToGAS } = require('./ocrRunner');
const sessionLogger = require('./sessionLogger');
const allowedNumbers = require('./allowedNumbers');

const IPHONE_IMAGE_EXTENSIONS = ['.heic', '.heif', '.dng', '.tiff', '.tif', '.jpg', '.jpeg', '.png', '.webp'];

function isIphoneOrStandardImage(mimetype = '', fileName = '') {
  const mime = (mimetype || '').toLowerCase();
  const ext = path.extname((fileName || '').toLowerCase());
  return (
    mime.startsWith('image/') ||
    mime.includes('heic') ||
    mime.includes('heif') ||
    mime.includes('dng') ||
    mime.includes('tiff') ||
    IPHONE_IMAGE_EXTENSIONS.includes(ext)
  );
}

const STATE_FILE = path.join(config.ROOT_DIR, 'runtime', 'scanner_state.json');

function loadScannerState() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      const data = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
      if (typeof data.active === 'boolean') {
        return data.active;
      }
    }
  } catch (err) {
    console.warn('⚠️ Gagal membaca scanner_state.json:', err.message);
  }
  return false;
}

function saveScannerState(active) {
  try {
    const dir = path.dirname(STATE_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(STATE_FILE, JSON.stringify({ active, updated_at: new Date().toISOString() }, null, 2), 'utf-8');
  } catch (err) {
    console.error('⚠️ Gagal menyimpan scanner_state.json:', err.message);
  }
}

let isScanningActive = loadScannerState();
const botSentMessageIds = new Set();

function recordBotSentMessage(msgId) {
  if (msgId) {
    botSentMessageIds.add(msgId);
  }
}

function getTutorialText(isSelfChat = false) {
  let tuto = `📖 *PANDUAN PENGGUNAAN WSCANER* 📖\n\n` +
    `1️⃣ *Mulai Pemindaian:* Ketik *#start*\n` +
    `   • Scanner aktif & sesi log baru dibuat.\n\n` +
    `2️⃣ *Kirim Foto Buletin/Majalah:*\n` +
    `   • Kirim 1 foto atau beberapa foto sekaligus.\n` +
    `   • Bot mengekstrak *Edisi*, *Bulan/Tahun*, *Judul Artikel*, *Penulis*, & *Surah*.\n` +
    `   • Foto otomatis diunggah ke Google Drive (*DB-WScan*).\n` +
    `   • Data langsung tersimpan di baris baru Google Spreadsheet.\n\n` +
    `3️⃣ *Cek Spreadsheet:* Ketik *#link*\n` +
    `   • Mendapatkan link langsung ke Google Sheet hasil rekap.\n\n` +
    `4️⃣ *Unduh Log Sesi:* Ketik *#log*\n` +
    `   • Mengunduh file log (.log) sesi scanner saat ini / sesi terakhir.\n\n` +
    `5️⃣ *Cek Status:* Ketik *#status*\n` +
    `   • Mengetahui apakah scanner sedang aktif atau berhenti.\n\n` +
    `6️⃣ *Selesai / Nonaktifkan:* Ketik *#stop*\n` +
    `   • Mengakhiri sesi pemindaian dan menutup file log.\n\n`;

  if (isSelfChat) {
    tuto += `🛠️ *Menu Manajemen User (Khusus IT):*\n` +
      `• *add <nomor>* - Tambah akses user (misal: *add +62 812 3456 7890*)\n` +
      `• *rem <nomor>* - Cabut akses user dari daftar izin\n` +
      `• *list* - Lihat daftar seluruh user yang memiliki izin\n\n`;
  }

  tuto += `💡 *Tips:* Ketik *#tuto* kapan saja untuk membaca kembali panduan ini.`;
  return tuto;
}

function formatSuccessReply(data, isPendingGas = false) {
  let reply = `✅ *Scan Berhasil!*\n\n`;
  const edisiStr = data.edition
    ? `${data.edition}${data.year_roman ? ` (Tahun ${data.year_roman})` : ''}`
    : '-';
  reply += `📖 *Edisi:* ${edisiStr}\n`;
  reply += `📅 *Bulan/Tahun:* ${data.date || '-'}\n\n`;

  if (data.articles && data.articles.length > 0) {
    data.articles.forEach((art, idx) => {
      reply += `${idx + 1}️⃣ *${art.title}*\n`;
      reply += `   👤 *Penulis:* ${art.author || '-'}\n`;
      if (art.surah && art.surah !== '-') {
        reply += `   📖 *Surah:* ${art.surah}\n`;
      }
      reply += `\n`;
    });
  } else {
    reply += `⚠️ Tidak ada artikel terdeteksi di sidebar.\n\n`;
  }

  if (!data.edition || data.edition === '-') {
    reply += `💡 *Tips Akurasi:* Bagian bawah cover (Edisi/Tahun) tidak terdeteksi. Pastikan seluruh lembar cover difoto penuh dan tidak terpotong.\n\n`;
  }

  if (isPendingGas) {
    if (config.GAS_WEBHOOK_URL) {
      reply += `📊 *Google Sheet & Drive:* ⏳ Menyimpan di latar belakang...\n_(Reaksi ✅ akan muncul jika data sudah tersimpan)_\n`;
    } else {
      reply += `ℹ️ (Google Sheet URL belum disetel di .env)\n`;
    }
  } else if (data.gas_response) {
    if (data.gas_response.status === 'success') {
      reply += `📊 *Tersimpan ke Google Sheet:* ✅ SUKSES\n`;
      if (data.gas_response.drive_file_url) {
        reply += `📁 *Foto Tersimpan di Drive:* [DB-WScan]\n`;
      }
    } else {
      const reason = data.gas_response.message || data.gas_response.error || `HTTP ${data.gas_response.http_code || 401}`;
      reply += `📊 *Tersimpan ke Google Sheet:* ❌ GAGAL (${reason})\n`;
    }
  } else if (config.GAS_WEBHOOK_URL) {
    reply += `📊 *Tersimpan ke Google Sheet:* ⚠️ Tidak ada respon dari server\n`;
  } else {
    reply += `ℹ️ (Google Sheet URL belum disetel di .env)\n`;
  }

  return reply;
}

async function sendBotReply(sock, remoteJid, content, options = {}) {
  try {
    const sent = await sock.sendMessage(remoteJid, content, options);
    if (sent && sent.key && sent.key.id) {
      botSentMessageIds.add(sent.key.id);
      if (botSentMessageIds.size > 150) {
        const first = botSentMessageIds.values().next().value;
        botSentMessageIds.delete(first);
      }
    }
    return sent;
  } catch (err) {
    console.error('❌ [ERROR] Gagal mengirim balasan WhatsApp:', err.message);
  }
}

function unwrapMessage(msg) {
  let m = msg.message;
  if (!m) return { text: '', isImage: false, rawImage: null, messageType: 'empty' };

  // Unwrap WhatsApp wrappers (ephemeral, viewOnce, document containers)
  if (m.ephemeralMessage) m = m.ephemeralMessage.message;
  if (m.viewOnceMessage) m = m.viewOnceMessage.message;
  if (m.viewOnceMessageV2) m = m.viewOnceMessageV2.message;
  if (m.documentWithCaptionMessage) m = m.documentWithCaptionMessage.message;

  const messageType = Object.keys(m || {})[0] || 'unknown';

  const text = (
    m?.conversation ||
    m?.extendedTextMessage?.text ||
    m?.imageMessage?.caption ||
    m?.documentMessage?.caption ||
    ''
  ).trim();

  const isImage = !!(
    m?.imageMessage ||
    (m?.documentMessage && isIphoneOrStandardImage(m.documentMessage.mimetype, m.documentMessage.fileName))
  );
  const rawImage = m?.imageMessage || m?.documentMessage;

  return { text, isImage, rawImage, messageType };
}

const imageQueue = [];
const gasQueue = [];
let isProcessingGas = false;
const OCR_CONCURRENCY_LIMIT = 2;
let activeOcrWorkers = 0;

function enqueueGASUpload(task) {
  gasQueue.push(task);
  processGASQueue().catch((err) => console.error('GAS Queue error:', err));
}

async function processGASQueue() {
  if (isProcessingGas) return;
  isProcessingGas = true;

  try {
    while (gasQueue.length > 0) {
      const task = gasQueue.shift();
      const { sock, remoteJid, replyKey, ocrData, quotedMsg } = task;

      try {
        sessionLogger.logToSession(`📊 Mulai sinkronisasi Google Sheet untuk Edisi ${ocrData.edition || '-'}...`);
        const tGasStart = Date.now();
        const gasRes = await syncToGAS(ocrData);
        const gasDur = ((Date.now() - tGasStart) / 1000).toFixed(1);
        ocrData.gas_response = gasRes;

        if (gasRes.status === 'success') {
          sessionLogger.logToSession(`📊 Sukses simpan ke Google Sheet (${gasDur}s) - Drive: ${gasRes.drive_file_url ? 'OK' : 'None'}`);
          console.log(`✅ [GAS SUCCESS] Data tersimpan ke Spreadsheet & Drive dalam ${gasDur}s`);
          if (replyKey) {
            try {
              await sock.sendMessage(remoteJid, {
                react: { text: '✅', key: replyKey }
              });
            } catch (reactErr) {
              // Ignore reaction error
            }
          }
        } else if (gasRes.status !== 'skipped') {
          const errReason = gasRes.message || gasRes.error || `HTTP ${gasRes.http_code || 500}`;
          sessionLogger.logToSession(`❌ Gagal simpan Google Sheet: ${errReason}`);
          console.error(`❌ [GAS ERROR] Gagal simpan: ${errReason}`);
          if (replyKey) {
            try {
              await sock.sendMessage(remoteJid, {
                react: { text: '⚠️', key: replyKey }
              });
            } catch (reactErr) {}
          }
          await sendBotReply(sock, remoteJid, {
            text: `⚠️ *Gagal Menyimpan ke Google Sheet:*\n${errReason}\n\n_(Hasil scan tetap tersimpan di log lokal bot)_`
          }, { quoted: quotedMsg });
        }
      } catch (err) {
        console.error('❌ [GAS SYNC ERROR]', err.message);
        sessionLogger.logToSession(`❌ Exception sync GAS: ${err.message}`);
      }
    }
  } finally {
    isProcessingGas = false;
  }
}

async function handleSingleImage(sock, item) {
  const { msg, remoteJid } = item;
  let filePath = null;

  try {
    if (!fs.existsSync(config.TEMP_DIR)) {
      fs.mkdirSync(config.TEMP_DIR, { recursive: true });
    }

    let buffer = await downloadMediaMessage(msg, 'buffer', {});
    const rawImage = msg.message?.imageMessage || msg.message?.documentMessage;
    const mime = (rawImage?.mimetype || '').toLowerCase();
    const docName = (rawImage?.fileName || '').toLowerCase();
    const isHeic = mime.includes('heic') || mime.includes('heif') || docName.endsWith('.heic') || docName.endsWith('.heif');

    if (isHeic && convertHeic) {
      try {
        console.log('[DEBUG] Mengonversi foto iPhone HEIC ke JPEG untuk OCR...');
        buffer = await convertHeic({
          buffer: buffer,
          format: 'JPEG',
          quality: 0.95
        });
      } catch (convErr) {
        console.warn('⚠️ Gagal konversi HEIC ke JPEG:', convErr.message);
      }
    }

    const fileName = `scan_${Date.now()}_${Math.random().toString(36).substring(2, 6)}.jpg`;
    filePath = path.join(config.TEMP_DIR, fileName);
    fs.writeFileSync(filePath, buffer);

    console.log(`[DEBUG] Foto disimpan di: ${filePath}`);
    sessionLogger.logToSession(`📸 Foto diterima & disimpan: ${fileName}`);

    const tOcr0 = Date.now();
    const ocrData = await runOCR(filePath);
    const ocrDur = ((Date.now() - tOcr0) / 1000).toFixed(2);
    console.log(`[DEBUG] Hasil OCR (${ocrDur}s):`, JSON.stringify({
      edition: ocrData.edition,
      date: ocrData.date,
      articles: (ocrData.articles || []).length
    }));

    if (ocrData.status !== 'success') {
      sessionLogger.logToSession(`❌ Gagal OCR: ${ocrData.message || 'Format tidak dikenali.'}`);
      await sendBotReply(sock, remoteJid, {
        text: `❌ *Gagal memproses gambar:* ${ocrData.message || 'Format tidak dikenali.'}`
      }, { quoted: msg });
      return;
    }

    const articleCount = (ocrData.articles || []).length;
    sessionLogger.logToSession(`✅ OCR Berhasil (${ocrDur}s) - Edisi: ${ocrData.edition || '-'}, Tanggal: ${ocrData.date || '-'}, Artikel: ${articleCount} judul`);

    // 1. Send instant WhatsApp response (< 1s)
    const replyText = formatSuccessReply(ocrData, true);
    const sentReply = await sendBotReply(sock, remoteJid, { text: replyText }, { quoted: msg });
    console.log(`⚡ [INSTANT REPLY] Respon terkirim ke WhatsApp dalam ${ocrDur}s untuk Edisi ${ocrData.edition || '-'}`);

    // 2. Queue background upload to Google Apps Script (Drive + Sheet)
    enqueueGASUpload({
      sock,
      remoteJid,
      replyKey: sentReply ? sentReply.key : null,
      ocrData,
      quotedMsg: msg
    });

  } catch (err) {
    console.error('❌ [DEBUG ERROR]', err.message);
    sessionLogger.logToSession(`❌ Error pemrosesan: ${err.message}`);
    await sendBotReply(sock, remoteJid, {
      text: `❌ *Gagal:* ${err.message}`
    }, { quoted: msg });
  } finally {
    if (filePath && fs.existsSync(filePath)) {
      try {
        fs.unlinkSync(filePath);
      } catch (cleanupErr) {
        // Ignore file cleanup warning
      }
    }
  }
}

function triggerNextOcrWorkers(sock) {
  while (imageQueue.length > 0 && activeOcrWorkers < OCR_CONCURRENCY_LIMIT) {
    const item = imageQueue.shift();
    activeOcrWorkers++;
    handleSingleImage(sock, item)
      .catch((err) => console.error('Image handling error:', err))
      .finally(() => {
        activeOcrWorkers--;
        triggerNextOcrWorkers(sock);
      });
  }
}

async function processQueue(sock) {
  triggerNextOcrWorkers(sock);
}

async function handleMessage(sock, msg) {
  if (!msg.message) return;

  const msgId = msg.key.id;
  const isFromMe = !!msg.key.fromMe;
  const remoteJid = msg.key.remoteJid || '';

  // 1. Skip messages sent by this bot itself
  if (botSentMessageIds.has(msgId)) {
    return;
  }

  // Extract content & handle WhatsApp wrappers
  const { text, isImage, messageType } = unwrapMessage(msg);

  // Skip WhatsApp internal background sync messages (protocol, reactions, receipts)
  if (['protocolMessage', 'reactionMessage', 'senderKeyDistributionMessage', 'empty'].includes(messageType)) {
    return;
  }

  // 1. Skip group chats
  if (remoteJid.endsWith('@g.us')) {
    return;
  }

  // 2. Determine user's own identity (Phone number and LID)
  const myJid = sock.user ? jidNormalizedUser(sock.user.id) : '';
  const myNumber = myJid.replace(/[^0-9]/g, '');
  const myLid = sock.user && sock.user.lid ? jidNormalizedUser(sock.user.lid) : '';
  const myLidNumber = myLid.replace(/[^0-9]/g, '');

  const normalizedRemote = jidNormalizedUser(remoteJid);
  const remoteNumber = normalizedRemote.replace(/[^0-9]/g, '');
  const participantNumber = (msg.key.participant || '').replace(/[^0-9]/g, '');

  // Check if this message is strictly within your own chat ("Message Yourself")
  const isSelfChat = isFromMe && (
    normalizedRemote === myJid ||
    (myNumber && remoteNumber === myNumber) ||
    (myLid && normalizedRemote === myLid) ||
    (myLidNumber && remoteNumber === myLidNumber) ||
    remoteJid === myJid ||
    (myNumber && remoteJid.startsWith(myNumber))
  );

  // CRITICAL RULE:
  // If the message is sent from your own phone (fromMe = true):
  // The bot MUST ONLY respond if it is in the chat with YOURSELF (isSelfChat = true)!
  // If you are chatting with ANY other contact/person/LID, IGNORE IT 100%!
  if (isFromMe && !isSelfChat) {
    return;
  }

  // For incoming messages from another phone (fromMe = false):
  const senderNumber = participantNumber || remoteNumber;
  const isIncomingFromAllowed = !isFromMe && allowedNumbers.isNumberAllowed(senderNumber, remoteNumber);

  // Must be either your own Self-Chat OR an incoming message from the allowed phone
  const isAuthorized = isSelfChat || isIncomingFromAllowed;
  const currentNumbers = allowedNumbers.getAllowedNumbers();
  const resolvedSenderPhone = allowedNumbers.resolveLidToPhone(senderNumber) || senderNumber;
  const authReason = isSelfChat
    ? 'Chat dengan diri sendiri (Owner)'
    : (isIncomingFromAllowed ? `Pesan masuk dari nomor diizinkan (+${resolvedSenderPhone})` : 'Nomor tidak diizinkan');

  if (!isAuthorized) {
    return;
  }

  const lowerText = text.toLowerCase();

  // 🔍 COMPREHENSIVE DEBUG LOG (Only for authorized bot interactions)
  console.log('\n================== 🔍 [DEBUG PESAN] ==================');
  console.log(`📩 ID Pesan      : ${msgId}`);
  console.log(`👤 fromMe        : ${isFromMe} (${isSelfChat ? 'Chat Diri Sendiri' : 'Pesan Masuk'})`);
  console.log(`👑 Otorisasi     : ✅ DISETUJUI (${authReason})`);
  console.log(`📍 remoteJid     : ${remoteJid}`);
  console.log(`📱 Nomor Akun WA : ${myNumber || '(Belum terdeteksi)'}`);
  console.log(`📲 Nomor Pengirim: ${isFromMe ? myNumber : '+' + resolvedSenderPhone}`);
  console.log(`🔒 NOMOR DIIZINKAN: ${currentNumbers.length > 0 ? currentNumbers.map(n => '+' + n).join(', ') : '(HANYA CHAT DIRI SENDIRI)'}`);
  console.log(`📦 Tipe Pesan WA : ${messageType}`);
  console.log(`💬 Isi Teks      : "${text}"`);
  console.log(`🖼️ Apakah Gambar : ${isImage}`);
  console.log(`⚡ Status Scanner: ${isScanningActive ? '🟢 AKTIF' : '🔴 NONAKTIF'}`);

  // Helper for matching commands with or without '#'
  const isCmd = (target) => {
    if (!target) return false;
    const clean = target.replace(/^#/, '').toLowerCase();
    return lowerText === `#${clean}` || lowerText === clean;
  };

  // 3. Handle Commands
  if (isCmd(config.START_COMMAND)) {
    isScanningActive = true;
    saveScannerState(true);
    sessionLogger.startSession();
    sessionLogger.logToSession('🟢 Sesi scanner diaktifkan oleh user.');
    console.log(`🟢 [DEBUG] Perintah START diterima! Mengaktifkan scanner & memulai sesi log.`);
    await sendBotReply(sock, remoteJid, {
      text: `🟢 *Scanner Ulul Albab AKTIF!*\nSesi baru telah dimulai & pencatatan log aktif.\n\n` + getTutorialText(isSelfChat)
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  if (isCmd(config.STOP_COMMAND)) {
    isScanningActive = false;
    saveScannerState(false);
    sessionLogger.logToSession('🔴 Sesi scanner dinonaktifkan oleh user.');
    const closedLog = sessionLogger.endSession();
    console.log(`🔴 [DEBUG] Perintah STOP diterima! Menonaktifkan scanner. Sesi tersimpan di: ${closedLog}`);
    await sendBotReply(sock, remoteJid, {
      text: `🔴 *Scanner Ulul Albab DINONAKTIFKAN.*\n\nSesi pemindaian telah selesai dan file log telah disimpan.\n\n` +
        `• Ketik *#log* untuk mengunduh log sesi ini.\n` +
        `• Ketik *#link* untuk membuka Google Spreadsheet.\n` +
        `• Ketik *#start* jika ingin memulai sesi baru.`
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  if (isCmd(config.STATUS_COMMAND)) {
    console.log(`ℹ️ [DEBUG] Perintah STATUS diterima.`);
    await sendBotReply(sock, remoteJid, {
      text: `ℹ️ *Status Scanner:* ${isScanningActive ? '🟢 AKTIF (Sesi sedang berjalan)' : '🔴 NONAKTIF'}\n\n` +
        `• Status: ${isScanningActive ? 'Sedang merekam sesi pemindaian' : 'Ketik *#start* untuk mulai'}\n` +
        `• Perintah: *#start*, *#stop*, *#status*, *#link*, *#log*, *#tuto*`
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  if (isCmd(config.LINK_COMMAND)) {
    console.log(`🔗 [DEBUG] Perintah LINK diterima.`);
    await sendBotReply(sock, remoteJid, {
      text: `📊 *Link Google Spreadsheet WScaner:*\n\n${config.SPREADSHEET_URL}\n\n_(Akses publik: Siapa saja yang memiliki link dapat melihat dan mengedit)_`
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  if (isCmd(config.LOG_COMMAND)) {
    console.log(`📄 [DEBUG] Perintah LOG diterima.`);
    const logFilePath = sessionLogger.getLatestLogFile();
    if (!logFilePath || !fs.existsSync(logFilePath)) {
      await sendBotReply(sock, remoteJid, {
        text: '⚠️ *Belum ada file log sesi.*\nSilakan ketik *#start* dan kirim beberapa foto terlebih dahulu.'
      }, { quoted: msg });
    } else {
      sessionLogger.logToSession(`📄 Pengiriman file log diminta user: ${path.basename(logFilePath)}`);
      const fileStats = fs.statSync(logFilePath);
      const fileName = path.basename(logFilePath);
      await sendBotReply(sock, remoteJid, {
        document: fs.readFileSync(logFilePath),
        mimetype: 'text/plain',
        fileName: fileName,
        caption: `📄 *File Log Sesi Scanner*\n\n📂 File: *${fileName}*\n⚖️ Ukuran: *${(fileStats.size / 1024).toFixed(1)} KB*\n⚡ Status Sesi: ${isScanningActive ? '🟢 Sedang Berjalan' : '🔴 Telah Berhenti'}`
      }, { quoted: msg });
    }
    console.log('======================================================\n');
    return;
  }

  if (isCmd(config.TUTO_COMMAND)) {
    console.log(`📖 [DEBUG] Perintah TUTO diterima.`);
    await sendBotReply(sock, remoteJid, {
      text: getTutorialText(isSelfChat)
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  // 3.7 Handle Add Number (IT Only)
  if (lowerText.startsWith('add') || lowerText.startsWith('#add')) {
    if (!isSelfChat) {
      console.log('⛔ [SECURITY] Percobaan perintah ADD dari akun non-IT!');
      await sendBotReply(sock, remoteJid, {
        text: '⛔ *Akses Ditolak!*\nPerintah menambah akses user hanya dapat dilakukan oleh IT di chat diri sendiri.'
      }, { quoted: msg });
      return;
    }

    const targetNum = text.replace(/^#?add\s*/i, '').trim();
    if (!targetNum) {
      await sendBotReply(sock, remoteJid, {
        text: 'ℹ️ *Format Perintah ADD (IT):*\nKetik *add <nomor>* untuk memberi izin kepada user.\nContoh: *add +62 812 3456 7890*'
      }, { quoted: msg });
      return;
    }

    const res = allowedNumbers.addNumber(targetNum);
    if (!res.success) {
      await sendBotReply(sock, remoteJid, {
        text: `❌ *Gagal Menambahkan:* ${res.error}`
      }, { quoted: msg });
    } else {
      sessionLogger.logToSession(`➕ IT menambahkan akses user: +${res.number}`);
      const listStr = res.numbers.map((n, i) => `${i + 1}. +${n}`).join('\n');
      await sendBotReply(sock, remoteJid, {
        text: `✅ *Akses User Berhasil Ditambahkan!*\n\nNomor: *+${res.number}*\n\n📋 *Daftar User Terdaftar (${res.numbers.length}):*\n${listStr}`
      }, { quoted: msg });
    }
    console.log('======================================================\n');
    return;
  }

  // 3.8 Handle Remove Number (IT Only)
  if (lowerText.startsWith('rem') || lowerText.startsWith('#rem') || lowerText.startsWith('remove') || lowerText.startsWith('#remove')) {
    if (!isSelfChat) {
      console.log('⛔ [SECURITY] Percobaan perintah REMOVE dari akun non-IT!');
      await sendBotReply(sock, remoteJid, {
        text: '⛔ *Akses Ditolak!*\nPerintah mencabut akses user hanya dapat dilakukan oleh IT di chat diri sendiri.'
      }, { quoted: msg });
      return;
    }

    const targetNum = text.replace(/^#(?:rem|remove)\s*|^(?:rem|remove)\s*/i, '').trim();
    if (!targetNum) {
      await sendBotReply(sock, remoteJid, {
        text: 'ℹ️ *Format Perintah REM (IT):*\nKetik *rem <nomor>* untuk mencabut izin user.\nContoh: *rem +62 812 3456 7890*'
      }, { quoted: msg });
      return;
    }

    const res = allowedNumbers.removeNumber(targetNum);
    if (!res.success) {
      await sendBotReply(sock, remoteJid, {
        text: `❌ *Gagal Menghapus:* ${res.error}`
      }, { quoted: msg });
    } else {
      sessionLogger.logToSession(`➖ IT mencabut akses user: +${res.number}`);
      const listStr = res.numbers.length > 0
        ? res.numbers.map((n, i) => `${i + 1}. +${n}`).join('\n')
        : '_(Tidak ada user luar, khusus akun IT)_';
      await sendBotReply(sock, remoteJid, {
        text: `🗑️ *Akses User Berhasil Dicabut!*\n\nNomor: *+${res.number}*\n\n📋 *Daftar User Terdaftar (${res.numbers.length}):*\n${listStr}`
      }, { quoted: msg });
    }
    console.log('======================================================\n');
    return;
  }

  // 3.9 Handle List Numbers (IT Only)
  if (isCmd('list') || isCmd('numbers') || isCmd('#list')) {
    if (!isSelfChat) {
      console.log('⛔ [SECURITY] Percobaan perintah LIST dari akun non-IT!');
      await sendBotReply(sock, remoteJid, {
        text: '⛔ *Akses Ditolak!*\nPerintah melihat daftar user hanya dapat dilakukan oleh IT di chat diri sendiri.'
      }, { quoted: msg });
      return;
    }

    const list = allowedNumbers.getAllowedNumbers();
    let reply = `📋 *Daftar User Terdaftar (${list.length}):*\n\n`;
    if (list.length > 0) {
      reply += list.map((n, i) => `${i + 1}. +${n}`).join('\n');
    } else {
      reply += `_(Belum ada user luar terdaftar, khusus akun IT)_`;
    }
    reply += `\n\n💡 *Perintah IT:* Ketik *add <nomor>* untuk menambah atau *rem <nomor>* untuk menghapus.`;
    await sendBotReply(sock, remoteJid, { text: reply }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  // 4. Handle Image
  if (isImage) {
    if (!isScanningActive) {
      console.log(`⚠️ [DEBUG] Gambar diabaikan karena scanner sedang NONAKTIF.`);
      await sendBotReply(sock, remoteJid, {
        text: `⚠️ *Scanner sedang nonaktif.*\nKetik *${config.START_COMMAND}* terlebih dahulu untuk mengaktifkan pemindaian.\nKetik *#tuto* untuk melihat panduan penggunaan.`
      }, { quoted: msg });
      console.log('======================================================\n');
      return;
    }

    imageQueue.push({ msg, remoteJid });
    const isWaitingInQueue = imageQueue.length > 1 || activeOcrWorkers >= OCR_CONCURRENCY_LIMIT;
    const queueDisplayPos = imageQueue.length + (activeOcrWorkers > 0 ? activeOcrWorkers : 0);
    sessionLogger.logToSession(`⏳ Foto masuk antrean ke-${imageQueue.length}`);

    if (isWaitingInQueue) {
      console.log(`⏳ [DEBUG] Foto ditambahkan ke antrean (Posisi ke-${queueDisplayPos}).`);
      await sendBotReply(sock, remoteJid, {
        text: `⏳ *Foto diterima!*\nMasuk antrean nomor *${queueDisplayPos}*. Akan diproses secara berurutan.`
      }, { quoted: msg });
    } else {
      console.log(`⏳ [DEBUG] Foto diterima! Mulai mengunduh & memproses OCR...`);
      await sendBotReply(sock, remoteJid, {
        text: '⏳ *Sedang memproses foto dengan OCR...*\nMohon tunggu beberapa detik.'
      }, { quoted: msg });
    }

    processQueue(sock).catch(err => console.error('Queue execution error:', err));
  }

  console.log('======================================================\n');
}

module.exports = { handleMessage, recordBotSentMessage };
