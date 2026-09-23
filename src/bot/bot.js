const { initWhatsAppBot } = require('./whatsapp');
const ocrDaemon = require('./ocrDaemon');

const engineName = (process.env.OCR_ENGINE || 'windows').toUpperCase();
console.log(`🚀 Memulai WScaner WhatsApp OCR Bot...`);
console.log(`🔍 Mesin Aktif: ${engineName}`);

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

