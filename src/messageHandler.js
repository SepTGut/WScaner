const { downloadMediaMessage, jidNormalizedUser } = require('@whiskeysockets/baileys');
const fs = require('fs');
const path = require('path');
const config = require('./config');
const { runOCR } = require('./ocrRunner');

let isScanningActive = false;
const botSentMessageIds = new Set();

function formatSuccessReply(data) {
  let reply = `✅ *Scan Berhasil!*\n\n`;
  reply += `📖 *Edisi:* ${data.edition || '-'}\n`;
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

  if (data.gas_response) {
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

  const isImage = !!(m?.imageMessage || (m?.documentMessage && m?.documentMessage?.mimetype?.startsWith('image/')));
  const rawImage = m?.imageMessage || m?.documentMessage;

  return { text, isImage, rawImage, messageType };
}

const imageQueue = [];
let isProcessingQueue = false;

async function handleSingleImage(sock, item) {
  const { msg, remoteJid } = item;

  try {
    if (!fs.existsSync(config.TEMP_DIR)) {
      fs.mkdirSync(config.TEMP_DIR, { recursive: true });
    }

    const buffer = await downloadMediaMessage(msg, 'buffer', {});
    const fileName = `scan_${Date.now()}.jpg`;
    const filePath = path.join(config.TEMP_DIR, fileName);
    fs.writeFileSync(filePath, buffer);

    console.log(`[DEBUG] Foto disimpan di: ${filePath}`);
    const ocrData = await runOCR(filePath);
    console.log(`[DEBUG] Hasil OCR:`, JSON.stringify(ocrData, null, 2));

    if (ocrData.status !== 'success') {
      await sendBotReply(sock, remoteJid, {
        text: `❌ *Gagal memproses gambar:* ${ocrData.message || 'Format tidak dikenali.'}`
      }, { quoted: msg });
      return;
    }

    const reply = formatSuccessReply(ocrData);
    await sendBotReply(sock, remoteJid, { text: reply }, { quoted: msg });
    console.log(`✅ [SUCCESS] Selesai memproses Edisi ${ocrData.edition}`);

  } catch (err) {
    console.error('❌ [DEBUG ERROR]', err.message);
    await sendBotReply(sock, remoteJid, {
      text: `❌ *Gagal:* ${err.message}`
    }, { quoted: msg });
  }
}

async function processQueue(sock) {
  if (isProcessingQueue) return;
  isProcessingQueue = true;

  while (imageQueue.length > 0) {
    const item = imageQueue.shift();
    await handleSingleImage(sock, item);
  }

  isProcessingQueue = false;
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
  const isIncomingFromAllowed = !isFromMe && config.ALLOWED_NUMBER && (
    senderNumber === config.ALLOWED_NUMBER || remoteNumber === config.ALLOWED_NUMBER
  );

  // Must be either your own Self-Chat OR an incoming message from the allowed phone
  const isAuthorized = isSelfChat || isIncomingFromAllowed;
  const authReason = isSelfChat
    ? 'Chat dengan diri sendiri (Owner)'
    : (isIncomingFromAllowed ? `Pesan masuk dari ${config.ALLOWED_NUMBER}` : 'Nomor tidak diizinkan');

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
  console.log(`📲 Nomor Pengirim: ${isFromMe ? myNumber : senderNumber}`);
  console.log(`🔒 ALLOWED_NUMBER: ${config.ALLOWED_NUMBER ? config.ALLOWED_NUMBER : '(HANYA CHAT DIRI SENDIRI)'}`);
  console.log(`📦 Tipe Pesan WA : ${messageType}`);
  console.log(`💬 Isi Teks      : "${text}"`);
  console.log(`🖼️ Apakah Gambar : ${isImage}`);
  console.log(`⚡ Status Scanner: ${isScanningActive ? '🟢 AKTIF' : '🔴 NONAKTIF'}`);

  // 3. Handle Commands
  if (lowerText === config.START_COMMAND) {
    isScanningActive = true;
    console.log(`🟢 [DEBUG] Perintah START diterima! Mengaktifkan scanner.`);
    await sendBotReply(sock, remoteJid, {
      text: `🟢 *Scanner Ulul Albab AKTIF!*\n\nSilakan kirimkan foto cover/artikel dakwah. Data akan otomatis diekstrak dan disimpan ke Google Sheet.\n\nKetik *${config.STOP_COMMAND}* untuk menonaktifkan.`
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  if (lowerText === config.STOP_COMMAND) {
    isScanningActive = false;
    console.log(`🔴 [DEBUG] Perintah STOP diterima! Menonaktifkan scanner.`);
    await sendBotReply(sock, remoteJid, {
      text: `🔴 *Scanner Ulul Albab DINONAKTIFKAN.*\n\nBot tidak akan memproses foto hingga Anda mengetik *${config.START_COMMAND}* kembali.`
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  if (lowerText === config.STATUS_COMMAND) {
    console.log(`ℹ️ [DEBUG] Perintah STATUS diterima.`);
    await sendBotReply(sock, remoteJid, {
      text: `ℹ️ *Status Scanner:* ${isScanningActive ? '🟢 AKTIF (Siap menerima foto)' : '🔴 NONAKTIF (Ketik ' + config.START_COMMAND + ' untuk mulai)'}`
    }, { quoted: msg });
    console.log('======================================================\n');
    return;
  }

  // 4. Handle Image
  if (isImage) {
    if (!isScanningActive) {
      console.log(`⚠️ [DEBUG] Gambar diabaikan karena scanner sedang NONAKTIF.`);
      await sendBotReply(sock, remoteJid, {
        text: `⚠️ *Scanner sedang nonaktif.*\nKetik *${config.START_COMMAND}* terlebih dahulu untuk mengaktifkan pemindaian.`
      }, { quoted: msg });
      console.log('======================================================\n');
      return;
    }

    imageQueue.push({ msg, remoteJid });
    const queuePosition = imageQueue.length;

    if (queuePosition > 1) {
      console.log(`⏳ [DEBUG] Foto ditambahkan ke antrean (Posisi ke-${queuePosition}).`);
      await sendBotReply(sock, remoteJid, {
        text: `⏳ *Foto diterima!*\nMasuk antrean nomor *${queuePosition}*. Akan diproses secara berurutan.`
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

module.exports = { handleMessage };
