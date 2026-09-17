const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const config = require('./config');
const { handleMessage } = require('./messageHandler');

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
      console.log('Koneksi terputus. Menghubungkan kembali...', shouldReconnect);
      if (shouldReconnect) {
        initWhatsAppBot();
      }
    } else if (connection === 'open') {
      console.log('======================================================');
      console.log('✅ WHATSAPP BERHASIL TERHUBUNG!');
      console.log(`📱 Nomor Diizinkan:   ${config.ALLOWED_NUMBER ? config.ALLOWED_NUMBER : '(SEMUA NOMOR / Belum disetel)'}`);
      console.log(`▶️  Perintah Mulai:    ${config.START_COMMAND}`);
      console.log(`⏹️  Perintah Berhenti: ${config.STOP_COMMAND}`);
      console.log(`📊 GAS Webhook:       ${config.GAS_WEBHOOK_URL ? 'TERHUBUNG' : 'BELUM DISETEL'}`);
      console.log('======================================================\n');
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
