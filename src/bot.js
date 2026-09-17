const { initWhatsAppBot } = require('./whatsapp');

console.log('🚀 Memulai WScaner WhatsApp OCR Bot...');

initWhatsAppBot().catch((err) => {
  console.error('❌ Gagal menjalankan WhatsApp Bot:', err);
});
