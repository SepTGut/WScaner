// Filter out noisy internal libsignal logs from Baileys
const IGNORED_LIBSIGNAL_LOGS = [
  'Closing session:',
  'Opening session:',
  'Session already closed',
  'Session already open',
  'Removing old closed session:',
  'Decrypted message with closed session.',
  'Closing open session in favor of incoming prekey bundle'
];

const originalWarn = console.warn;
console.warn = function (...args) {
  if (typeof args[0] === 'string' && IGNORED_LIBSIGNAL_LOGS.some(p => args[0].includes(p))) {
    return;
  }
  originalWarn.apply(console, args);
};

const originalInfo = console.info;
console.info = function (...args) {
  if (typeof args[0] === 'string' && IGNORED_LIBSIGNAL_LOGS.some(p => args[0].includes(p))) {
    return;
  }
  originalInfo.apply(console, args);
};

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  downloadMediaMessage,
  jidNormalizedUser
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const fs = require('fs');
const path = require('path');
const readline = require('readline');
let convertHeic = null;
try {
  convertHeic = require('heic-convert');
} catch (e) {}

const config = require('./config');
const allowedNumbers = require('./allowedNumbers');

const IPHONE_IMAGE_EXTENSIONS = ['.heic', '.heif', '.dng', '.tiff', '.tif', '.jpg', '.jpeg', '.png', '.webp'];

function normalizePhone(num) {
  if (!num) return '';
  let cleaned = String(num).replace(/[^0-9]/g, '');
  if (cleaned.startsWith('0')) {
    cleaned = '62' + cleaned.slice(1);
  }
  return cleaned;
}

function isSameDay(timestamp, targetDate = new Date()) {
  if (!timestamp) return false;
  let ts = timestamp;
  if (typeof ts === 'object' && ts !== null) {
    ts = ts.low !== undefined ? ts.low : Number(ts);
  }
  ts = Number(ts);
  if (isNaN(ts) || ts <= 0) return false;
  // Baileys timestamps are in seconds
  if (ts < 1e12) {
    ts = ts * 1000;
  }
  const msgDate = new Date(ts);
  return (
    msgDate.getFullYear() === targetDate.getFullYear() &&
    msgDate.getMonth() === targetDate.getMonth() &&
    msgDate.getDate() === targetDate.getDate()
  );
}

function isWithin24Hours(timestamp) {
  if (!timestamp) return false;
  let ts = timestamp;
  if (typeof ts === 'object' && ts !== null) {
    ts = ts.low !== undefined ? ts.low : Number(ts);
  }
  ts = Number(ts);
  if (isNaN(ts) || ts <= 0) return false;
  if (ts < 1e12) {
    ts = ts * 1000;
  }
  return (Date.now() - ts) <= (24 * 60 * 60 * 1000);
}

/**
 * Check if the mimetype or filename matches standard or iPhone image formats
 * (HEIC, HEIF, DNG/ProRAW, TIFF, JPEG, PNG, WebP).
 */
function isIphoneOrStandardImage(mimetype = '', fileName = '') {
  const mime = (mimetype || '').toLowerCase();
  const ext = path.extname((fileName || '').toLowerCase());

  if (
    mime.startsWith('image/') ||
    mime.includes('heic') ||
    mime.includes('heif') ||
    mime.includes('dng') ||
    mime.includes('tiff')
  ) {
    return true;
  }

  if (IPHONE_IMAGE_EXTENSIONS.includes(ext)) {
    return true;
  }

  return false;
}

function extractImageInfo(msg) {
  let m = msg?.message;
  if (!m) return null;

  // Unwrap WhatsApp wrappers (ephemeral, viewOnce, document containers)
  if (m.ephemeralMessage) m = m.ephemeralMessage.message;
  if (m.viewOnceMessage) m = m.viewOnceMessage.message;
  if (m.viewOnceMessageV2) m = m.viewOnceMessageV2.message;
  if (m.documentWithCaptionMessage) m = m.documentWithCaptionMessage.message;

  if (m?.imageMessage) {
    return {
      type: 'image',
      mimetype: m.imageMessage.mimetype || 'image/jpeg',
      caption: m.imageMessage.caption || '',
      fileName: '',
      raw: m.imageMessage
    };
  }

  if (m?.documentMessage) {
    const mime = (m.documentMessage.mimetype || '').toLowerCase();
    const fileName = m.documentMessage.fileName || '';

    if (isIphoneOrStandardImage(mime, fileName)) {
      return {
        type: 'document-image',
        mimetype: mime,
        caption: m.documentMessage.caption || '',
        fileName: fileName,
        raw: m.documentMessage
      };
    }
  }

  return null;
}

function determineFileExtension(imgInfo) {
  const mime = (imgInfo.mimetype || '').toLowerCase();
  const fileName = (imgInfo.fileName || '').toLowerCase();
  const rawExt = path.extname(fileName);

  if (rawExt && IPHONE_IMAGE_EXTENSIONS.includes(rawExt)) {
    return rawExt;
  }

  if (mime.includes('heic')) return '.heic';
  if (mime.includes('heif')) return '.heif';
  if (mime.includes('dng')) return '.dng';
  if (mime.includes('png')) return '.png';
  if (mime.includes('webp')) return '.webp';
  if (mime.includes('tiff') || mime.includes('tif')) return '.tiff';
  if (mime.includes('jpeg') || mime.includes('jpg')) return '.jpg';

  return '.jpg';
}

function matchesTargetNumber(msg, targetPhone, myPhone = '', options = {}) {
  if (!targetPhone) return false;
  const normTarget = normalizePhone(targetPhone);
  if (!normTarget) return false;

  const remoteJid = msg.key?.remoteJid || '';
  const participant = msg.key?.participant || '';
  const fromMe = !!msg.key?.fromMe;

  const remoteDigits = remoteJid.replace(/@.*$/, '').replace(/[^0-9]/g, '');
  const participantDigits = participant.replace(/@.*$/, '').replace(/[^0-9]/g, '');

  const normRemote = normalizePhone(remoteDigits);
  const normParticipant = normalizePhone(participantDigits);

  // Check direct phone match
  if (normParticipant === normTarget) return true;
  if (normRemote === normTarget) {
    if (!fromMe || options.includeOutgoing) return true;
  }

  // Check target LID match
  const targetLid = allowedNumbers.resolvePhoneToLid(normTarget);
  if (targetLid) {
    if (remoteDigits === targetLid || participantDigits === targetLid) {
      if (!fromMe || options.includeOutgoing) return true;
    }
  }

  // Check LID resolution to phone
  try {
    const resolvedRemote = normalizePhone(allowedNumbers.resolveLidToPhone(remoteDigits) || '');
    const resolvedParticipant = normalizePhone(allowedNumbers.resolveLidToPhone(participantDigits) || '');
    if (resolvedParticipant === normTarget) return true;
    if (resolvedRemote === normTarget) {
      if (!fromMe || options.includeOutgoing) return true;
    }
  } catch (e) {}

  // If target is user's own number
  if (normTarget === myPhone) {
    if (fromMe && (normRemote === myPhone || remoteJid.includes(myPhone) || !remoteDigits)) {
      return true;
    }
  }

  return false;
}

/**
 * Interactive prompt: lets the user select from known numbers or type a new number.
 */
async function promptForTargetNumber(cliArg) {
  if (cliArg) {
    const norm = normalizePhone(cliArg);
    if (norm) return norm;
  }

  const knownNumbers = [...new Set([
    ...(config.ALLOWED_NUMBER ? [config.ALLOWED_NUMBER] : []),
    ...allowedNumbers.getAllowedNumbers()
  ])];

  while (true) {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    console.log('======================================================');
    console.log('📱 PILIH ATAU INPUT NOMOR WHATSAPP TARGET');
    console.log('======================================================');

    if (knownNumbers.length > 0) {
      console.log('Daftar nomor yang tersimpan:');
      knownNumbers.forEach((num, idx) => {
        console.log(`  [${idx + 1}] +${num}`);
      });
      console.log('------------------------------------------------------');
      console.log('💡 Ketik nomor pilihan (1, 2, ...) ATAU ketik nomor baru (contoh: 081234567890)');
    } else {
      console.log('💡 Masukkan nomor WhatsApp (contoh: 081234567890 atau 6281234567890)');
    }

    const answer = await new Promise((resolve) => {
      rl.question('\n👉 Pilihan / Nomor Anda: ', (ans) => {
        rl.close();
        resolve(ans.trim());
      });
    });

    if (!answer) {
      console.log('⚠️ Input tidak boleh kosong, silakan coba lagi.\n');
      continue;
    }

    const selectedIndex = parseInt(answer, 10);
    if (!isNaN(selectedIndex) && selectedIndex >= 1 && selectedIndex <= knownNumbers.length && answer.length <= 2) {
      return knownNumbers[selectedIndex - 1];
    }

    const norm = normalizePhone(answer);
    if (norm && norm.length >= 9 && norm.length <= 16) {
      return norm;
    }

    console.log('❌ Format nomor tidak valid. Minimal 9 digit angka (contoh: 081234567890). Silakan coba lagi.\n');
  }
}

/**
 * Request history sync from phone for a specific JID.
 */
async function requestChatHistory(sock, jid, count = 50) {
  if (!sock || !jid) return;
  try {
    console.log(`📲 Mengirim permintaan riwayat chat ke HP utama untuk: ${jid}...`);
    await sock.fetchMessageHistory(count, {
      remoteJid: jid,
      fromMe: false,
      id: ''
    }, Date.now());
    console.log(`✅ Permintaan riwayat terkirim ke HP utama (${jid}).`);
  } catch (err) {
    console.warn(`⚠️ Catatan: Tidak dapat meminta riwayat via PDO (${err.message})`);
  }
}

/**
 * Onetimeused - One-time function & script to fetch images/photos from a specific number sent today
 * and save them into GetDataFolder (Supports iPhone HEIC, HEIF, ProRAW DNG, TIFF, JPG, PNG).
 *
 * @param {string|object} [targetNumberOrOptions] - Target phone number (string) or options object
 * @param {object} [maybeOptions] - Options when targetNumber is provided as first arg
 * @returns {Promise<{ success: boolean, count: number, files: Array, folder: string }>}
 */
async function Onetimeused(targetNumberOrOptions, maybeOptions = {}) {
  let targetNumber = '';
  let options = {};

  if (typeof targetNumberOrOptions === 'object' && targetNumberOrOptions !== null) {
    options = targetNumberOrOptions;
    targetNumber = options.targetNumber || options.number || '';
  } else {
    targetNumber = targetNumberOrOptions || '';
    options = maybeOptions || {};
  }

  // If targetNumber is not provided directly, prompt the user with interactive choice/input
  if (!targetNumber) {
    if (process.argv[2]) {
      targetNumber = process.argv[2];
    } else {
      targetNumber = await promptForTargetNumber();
    }
  }

  const normTarget = normalizePhone(targetNumber);
  if (!normTarget) {
    throw new Error('❌ Nomor target WhatsApp tidak ditentukan atau tidak valid.');
  }

  const targetDate = options.targetDate ? new Date(options.targetDate) : new Date();
  const outputDir = options.outputFolder || config.GETDATA_DIR || path.join(config.ROOT_DIR, 'data', 'downloads');

  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const waitTimeoutMs = options.waitTimeoutMs || 35000;
  const idleTimeoutMs = options.idleTimeoutMs || 15000;

  console.log('\n======================================================');
  console.log('📸 [Onetimeused] MEMULAI PENGAMBILAN FOTO SATU KALI');
  console.log(`🎯 Nomor Target : +${normTarget}`);
  console.log(`📅 Tanggal      : ${targetDate.toLocaleDateString('id-ID')} (Hari Ini)`);
  console.log(`📁 Folder Simpan: ${outputDir}`);
  console.log(`🍏 Dukungan iPhone: HEIC, HEIF, ProRAW DNG, TIFF, JPG, PNG`);
  console.log('======================================================\n');

  const savedFiles = [];
  const processedMsgIds = new Set();
  let sock = options.sock;
  let isOwnSocket = false;
  let myPhone = '';
  let targetLid = allowedNumbers.resolvePhoneToLid(normTarget);

  return new Promise(async (resolve, reject) => {
    let idleTimer = null;
    let maxTimer = null;
    let isFinished = false;
    let rlKeypress = null;

    const finish = () => {
      if (isFinished) return;
      isFinished = true;

      if (idleTimer) clearTimeout(idleTimer);
      if (maxTimer) clearTimeout(maxTimer);
      if (rlKeypress) {
        try { rlKeypress.close(); } catch (e) {}
      }

      console.log('\n======================================================');
      console.log(`🎉 [Onetimeused] SELESAI!`);
      console.log(`📊 Total foto tersimpan: ${savedFiles.length}`);
      console.log(`📁 Lokasi: ${outputDir}`);
      if (savedFiles.length === 0) {
        console.log('\n💡 TIPS JIKA MASIH 0 FOTO:');
        console.log('1. Buka aplikasi WhatsApp di HP Anda agar HP aktif mengirim riwayat chat.');
        console.log('2. Atau Anda bisa langsung meneruskan (forward) foto yang diinginkan ke chat bot/diri sendiri.');
      }
      console.log('======================================================\n');

      if (isOwnSocket && sock) {
        try {
          console.log('🔌 Menutup koneksi WhatsApp...');
          sock.ws?.close();
        } catch (e) {}
      }

      resolve({
        success: true,
        count: savedFiles.length,
        files: savedFiles,
        folder: outputDir
      });
    };

    const resetIdleTimer = () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        console.log(`⏱️ Tidak ada aktivitas baru dalam ${idleTimeoutMs / 1000}s. Menyelesaikan proses...`);
        finish();
      }, idleTimeoutMs);
    };

    async function handleMessageItem(msg) {
      if (!msg?.message) return;
      const msgId = msg.key?.id;
      if (!msgId || processedMsgIds.has(msgId)) return;

      const remoteJid = msg.key?.remoteJid || '';
      const isFromTarget = matchesTargetNumber(msg, normTarget, myPhone, options);
      const isDateToday = isSameDay(msg.messageTimestamp, targetDate);
      const isRecent24h = isWithin24Hours(msg.messageTimestamp);
      const isDateValid = isDateToday || isRecent24h;

      // Check if message contains an image
      const imgInfo = extractImageInfo(msg);

      if (isFromTarget && imgInfo) {
        console.log(`🔍 [TERDETEKSI] Foto dari target (+${normTarget}) - ID: ${msgId}, Tanggal Cocok: ${isDateValid ? 'YA' : 'TIDAK'}`);
      }

      if (!isFromTarget || !isDateValid || !imgInfo) {
        return;
      }

      processedMsgIds.add(msgId);
      resetIdleTimer();

      try {
        console.log(`📥 Mengunduh foto (ID: ${msgId})...`);
        const buffer = await downloadMediaMessage(msg, 'buffer', {});
        if (!buffer || buffer.length === 0) {
          console.warn(`⚠️ Buffer kosong untuk foto ID ${msgId}`);
          return;
        }

        const ext = determineFileExtension(imgInfo);
        const ts = (typeof msg.messageTimestamp === 'object' && msg.messageTimestamp?.low !== undefined
          ? msg.messageTimestamp.low
          : Number(msg.messageTimestamp)) * 1000;
        const dateObj = new Date(ts);
        const yyyy = dateObj.getFullYear();
        const mm = String(dateObj.getMonth() + 1).padStart(2, '0');
        const dd = String(dateObj.getDate()).padStart(2, '0');
        const hh = String(dateObj.getHours()).padStart(2, '0');
        const min = String(dateObj.getMinutes()).padStart(2, '0');
        const ss = String(dateObj.getSeconds()).padStart(2, '0');
        const timeStr = `${yyyy}${mm}${dd}_${hh}${min}${ss}`;
        const cleanId = msgId.replace(/[^a-zA-Z0-9]/g, '').slice(-6);

        // Save original file (e.g. .heic, .dng, .jpg, .png)
        const fileName = `foto_${normTarget}_${timeStr}_${cleanId}${ext}`;
        const destPath = path.join(outputDir, fileName);

        fs.writeFileSync(destPath, buffer);
        console.log(`✅ Foto tersimpan: ${fileName} (${(buffer.length / 1024).toFixed(1)} KB)`);

        const fileRecord = {
          id: msgId,
          fileName,
          path: destPath,
          format: ext.replace('.', '').toUpperCase(),
          sizeBytes: buffer.length,
          timestamp: ts,
          caption: imgInfo.caption
        };

        // If iPhone HEIC/HEIF, also create a converted JPEG copy for universal preview
        if ((ext === '.heic' || ext === '.heif') && convertHeic) {
          try {
            console.log(`🔄 Mengonversi format iPhone HEIC ke JPEG untuk kompatibilitas...`);
            const jpegBuffer = await convertHeic({
              buffer: buffer,
              format: 'JPEG',
              quality: 0.95
            });
            const jpgFileName = `foto_${normTarget}_${timeStr}_${cleanId}.jpg`;
            const jpgPath = path.join(outputDir, jpgFileName);
            fs.writeFileSync(jpgPath, jpegBuffer);
            console.log(`✅ Salinan JPEG berhasil dibuat: ${jpgFileName} (${(jpegBuffer.length / 1024).toFixed(1)} KB)`);
            fileRecord.jpgPath = jpgPath;
          } catch (convErr) {
            console.warn(`⚠️ Catatan: Konversi HEIC ke JPEG dilewati (${convErr.message})`);
          }
        }

        savedFiles.push(fileRecord);
      } catch (err) {
        console.warn(`⚠️ Gagal mengunduh foto ID ${msgId}: ${err.message}`);
      }
    }

    try {
      if (!sock) {
        isOwnSocket = true;
        const { state, saveCreds } = await useMultiFileAuthState(config.AUTH_DIR);
        sock = makeWASocket({
          auth: state,
          logger: pino({ level: 'silent' }),
          printQRInTerminal: true,
          syncFullHistory: true
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', async (update) => {
          const { connection, lastDisconnect } = update;
          if (connection === 'open') {
            const myJid = sock.user ? jidNormalizedUser(sock.user.id) : '';
            myPhone = myJid.replace(/[^0-9]/g, '');
            console.log(`✅ Terhubung ke WhatsApp (Akun: +${myPhone || 'OK'})`);
            console.log(`🔍 Target nomor: +${normTarget}${targetLid ? ` (LID: ${targetLid})` : ''}`);

            // 1. Actively request chat history from primary phone
            const targetJid = `${normTarget}@s.whatsapp.net`;
            await requestChatHistory(sock, targetJid, 50);

            if (targetLid) {
              await requestChatHistory(sock, `${targetLid}@lid`, 50);
            }

            console.log('\n💡 PANDUAN PENTING:');
            console.log('   1. Pastikan WhatsApp di HP Anda sedang AKTIF/DIBUKA agar HP segera mengirim riwayat.');
            console.log('   2. Anda juga bisa meneruskan (forward) foto ke chat bot sekarang juga.');
            console.log('   3. Tekan [ENTER] kapan saja untuk mengakhiri pencarian lebih cepat.\n');

            resetIdleTimer();

            maxTimer = setTimeout(() => {
              console.log(`⏱️ Batas waktu maksimum (${waitTimeoutMs / 1000}s) tercapai.`);
              finish();
            }, waitTimeoutMs);

            // Allow pressing ENTER in console to finish immediately
            if (require.main === module) {
              rlKeypress = readline.createInterface({
                input: process.stdin,
                output: process.stdout
              });
              rlKeypress.on('line', () => {
                console.log('🛑 Dihentikan oleh pengguna.');
                finish();
              });
            }

          } else if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            if (statusCode === DisconnectReason.loggedOut) {
              console.error('❌ Sesi WhatsApp telah keluar (Logged Out).');
              reject(new Error('WhatsApp session logged out'));
            } else if (!isFinished) {
              console.log('ℹ️ Koneksi ditutup.');
              finish();
            }
          }
        });
      } else {
        const myJid = sock.user ? jidNormalizedUser(sock.user.id) : '';
        myPhone = myJid.replace(/[^0-9]/g, '');

        const targetJid = `${normTarget}@s.whatsapp.net`;
        await requestChatHistory(sock, targetJid, 50);
        if (targetLid) {
          await requestChatHistory(sock, `${targetLid}@lid`, 50);
        }

        resetIdleTimer();
        maxTimer = setTimeout(finish, waitTimeoutMs);
      }

      sock.ev.on('messaging-history.set', async ({ messages, syncType }) => {
        console.log(`📦 [SYNC] Menerima riwayat pesan (${messages?.length || 0} pesan, tipe: ${syncType || 'general'})...`);
        if (Array.isArray(messages)) {
          for (const msg of messages) {
            await handleMessageItem(msg);
          }
        }
      });

      sock.ev.on('messages.upsert', async ({ messages, type }) => {
        console.log(`📩 [PESAN MASUK] Menerima ${messages?.length || 0} pesan (tipe: ${type})...`);
        if (Array.isArray(messages)) {
          for (const msg of messages) {
            await handleMessageItem(msg);
          }
        }
      });

    } catch (err) {
      reject(err);
    }
  });
}

// Allow direct CLI execution: node src/oneTimeUsed.js [targetNumber]
if (require.main === module) {
  Onetimeused()
    .then((res) => {
      console.log(`\nSelesai: ${res.count} foto berhasil diekstrak ke ${res.folder}`);
      process.exit(0);
    })
    .catch((err) => {
      console.error('\nError saat menjalankan Onetimeused:', err.message);
      process.exit(1);
    });
}

module.exports = { Onetimeused };
