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

      // Send startup notification directly to owner's self-chat
      if (myJid) {
        const timeStr = new Date().toLocaleString('id-ID');
        let notifText = `🟢 *WScaner Bot Berhasil Berjalan!*\n\n` +
          `⏰ *Waktu Aktif:* ${timeStr}\n` +
          `📱 *Akun Bot:* +${myNumber}\n`;

        if (allowedList.length > 0) {
          notifText += `👥 *Nomor Diizinkan (${allowedList.length}):*\n` +
            allowedList.map((n, i) => `   ${i + 1}. +${n}`).join('\n') + `\n\n`;
        } else {
          notifText += `🔒 *Akses:* Khusus Chat Diri Sendiri (Owner)\n\n`;
        }

        notifText += `💡 *Perintah Tersedia:*\n` +
          `• *#start* - Mulai & aktifkan pemindaian\n` +
          `• *add <nomor>* - Tambah nomor yang diizinkan\n` +
          `• *rem <nomor>* - Hapus nomor dari daftar izin\n` +
          `• *list* - Lihat daftar nomor yang diizinkan\n` +
          `• *#tuto* - Panduan lengkap`;

        sock.sendMessage(myJid, { text: notifText })
          .then((sent) => {
            if (sent?.key?.id) {
              recordBotSentMessage(sent.key.id);
            }
            console.log('📬 [NOTIF] Notifikasi startup berhasil dikirim ke chat diri sendiri.');
          })
          .catch((err) => {
            console.error('⚠️ Gagal mengirim notifikasi startup ke chat diri sendiri:', err.message);
          });
      }
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

module.exports = { initWhatsAppBot };
