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

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, jidNormalizedUser } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const config = require('./config');
const allowedNumbers = require('./allowedNumbers');
const { handleMessage, recordBotSentMessage } = require('./messageHandler');

async function initWhatsAppBot() {
  const { state, saveCreds } = await useMultiFileAuthState(config.AUTH_DIR);

  const sock = makeWASocket({
    auth: state,
    logger: pino({ level: 'silent' }),
    printQRInTerminal: false
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\n======================================================');
      console.log('📌 SCAN QR CODE INI MENGGUNAKAN WHATSAPP DI HP ANDA:');
      console.log('   (Buka WhatsApp > Perangkat Tertaut > Tautkan Perangkat)');
      console.log('======================================================\n');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'close') {
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log('Koneksi terputus. Menghubungkan kembali dalam 3 detik...', shouldReconnect);
      if (shouldReconnect) {
        setTimeout(() => {
          initWhatsAppBot().catch(e => console.error('Error saat rekoneksi bot:', e.message));
        }, 3000);
      }
    } else if (connection === 'open') {
      const myJid = sock.user ? jidNormalizedUser(sock.user.id) : null;
      const myNumber = myJid ? myJid.replace(/[^0-9]/g, '') : '';
      const allowedList = allowedNumbers.getAllowedNumbers();

      console.log('======================================================');
      console.log('✅ WHATSAPP BERHASIL TERHUBUNG!');
      console.log(`📱 Nomor Akun WA:     ${myNumber ? '+' + myNumber : '(Belum terdeteksi)'}`);
      console.log(`👥 Nomor Diizinkan:   ${allowedList.length > 0 ? allowedList.map(n => '+' + n).join(', ') : '(Hanya chat diri sendiri)'}`);
      console.log(`▶️  Perintah Mulai:    ${config.START_COMMAND}`);
      console.log(`⏹️  Perintah Berhenti: ${config.STOP_COMMAND}`);
      console.log(`📊 GAS Webhook:       ${config.GAS_WEBHOOK_URL ? 'TERHUBUNG' : 'BELUM DISETEL'}`);
      console.log('======================================================\n');

      // Send startup notification with delay for session readiness
      sendStartupNotification(sock);
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    // Process both incoming ('notify') and self-synced ('append') messages
    for (const msg of messages) {
      await handleMessage(sock, msg);
    }
  });

  return sock;
}

let lastStartupNotifTime = 0;

async function sendStartupNotification(sock) {
  const now = Date.now();
  // Debounce: don't re-send if sent within the last 30 seconds (prevents spam on quick reconnects)
  if (now - lastStartupNotifTime < 30000) {
    return;
  }
  lastStartupNotifTime = now;

  // Crucial: Wait 4 seconds for Baileys to finish key exchange & initial session handshake
  await new Promise((r) => setTimeout(r, 4000));

  if (!sock.user) return;

  const myJid = jidNormalizedUser(sock.user.id);
  const myLid = sock.user.lid ? jidNormalizedUser(sock.user.lid) : null;
  const myNumber = myJid ? myJid.replace(/[^0-9]/g, '') : '';
  const allowedList = allowedNumbers.getAllowedNumbers();
  const timeStr = new Date().toLocaleString('id-ID');

  let notifText = `🟢 *WScaner Bot Berhasil Berjalan!*\n\n` +
    `⏰ *Waktu Aktif:* ${timeStr}\n` +
    `🛠️ *Akun IT (Owner):* +${myNumber}\n`;

  if (allowedList.length > 0) {
    notifText += `👥 *User Diizinkan (${allowedList.length}):*\n` +
      allowedList.map((n, i) => `   ${i + 1}. +${n}`).join('\n') + `\n\n`;
  } else {
    notifText += `🔒 *Akses User:* Belum ada (Khusus IT)\n\n`;
  }

  notifText += `💡 *Perintah IT:*\n` +
    `• *#start* - Mulai & aktifkan pemindaian\n` +
    `• *add <nomor>* - Beri akses ke nomor user\n` +
    `• *rem <nomor>* - Cabut akses nomor user\n` +
    `• *list* - Lihat daftar nomor user\n` +
    `• *#status* - Cek status scanner\n` +
    `• *#tuto* - Panduan lengkap`;

  // Send ONLY to IT self-chat (try phone JID, then LID fallback)
  const selfTargets = [myJid];
  if (myLid && myLid !== myJid) {
    selfTargets.push(myLid);
  }

  let sentSelf = false;
  for (const target of selfTargets) {
    if (!target) continue;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        console.log(`📬 [NOTIF] Mengirim notifikasi startup ke akun IT (${target}, percobaan ${attempt})...`);
        const sent = await sock.sendMessage(target, { text: notifText });
        if (sent?.key?.id) {
          recordBotSentMessage(sent.key.id);
        }
        console.log(`✅ [NOTIF] Notifikasi startup berhasil terkirim ke akun IT!`);
        sentSelf = true;
        break;
      } catch (err) {
        console.warn(`⚠️ [NOTIF] Percobaan ${attempt} ke ${target} gagal: ${err.message}`);
        if (attempt < 3) {
          await new Promise((r) => setTimeout(r, 2500));
        }
      }
    }
    if (sentSelf) break;
  }
}

module.exports = { initWhatsAppBot };
