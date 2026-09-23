const { initWhatsAppBot } = require('./whatsapp');
const ocrDaemon = require('./ocrDaemon');

console.log('🚀 Memulai WScaner WhatsApp OCR Bot...');

(async () => {
  try {
    await ocrDaemon.start();
  } catch (err) {
    console.warn('⚠️ Gagal memulai OCR Daemon:', err.message);
  }

  initWhatsAppBot().catch((err) => {
    console.error('❌ Gagal menjalankan WhatsApp Bot:', err);
  });
})();

