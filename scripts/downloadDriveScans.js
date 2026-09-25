const fs = require('fs');
const path = require('path');
const axios = require('axios');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const OUTPUT_DIR = path.join(__dirname, '..', 'data', 'scans');

async function downloadAll() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const webhookUrl = process.env.GAS_WEBHOOK_URL;
  if (!webhookUrl) {
    console.error('GAS_WEBHOOK_URL not configured');
    process.exit(1);
  }

  const secret = process.env.GAS_SECRET_TOKEN || '';
  const postPayload = (payload) => (secret ? { ...payload, secret } : payload);

  console.log('📋 Fetching file list from Google Drive (DB-WScan)...');
  const listRes = await axios.post(webhookUrl, postPayload({ action: 'list_drive' }), { maxRedirects: 5, timeout: 30000 });
  
  if (listRes.data.status !== 'success') {
    console.error('Failed to list drive files:', listRes.data);
    process.exit(1);
  }

  const files = listRes.data.files;
  console.log(`Found ${files.length} files. Starting download...\n`);

  const manifest = [];

  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    console.log(`[${i + 1}/${files.length}] Downloading: ${f.name} (${f.sizeKb}) [ID: ${f.id}]...`);
    
    // Clean filename for safety
    const safeName = f.name.replace(/[^a-zA-Z0-9._\-()]/g, '_');
    const localPath = path.join(OUTPUT_DIR, `${String(i + 1).padStart(2, '0')}_${safeName}`);

    // Fetch base64 from GAS
    try {
      const fileRes = await axios.post(webhookUrl, postPayload({
        action: 'get_file_base64',
        file_id: f.id
      }), { maxRedirects: 5, timeout: 60000 });

      if (fileRes.data.status === 'success' && fileRes.data.base64) {
        const buffer = Buffer.from(fileRes.data.base64, 'base64');
        fs.writeFileSync(localPath, buffer);
        console.log(`   ✅ Saved to: ${path.basename(localPath)} (${(buffer.length / 1024).toFixed(1)} KB)`);
        manifest.push({
          index: i + 1,
          name: f.name,
          localFile: path.basename(localPath),
          localPath,
          id: f.id,
          sizeBytes: buffer.length,
          url: f.url,
          created: f.created
        });
      } else {
        console.error(`   ❌ Failed to get base64 for ${f.name}:`, fileRes.data);
      }
    } catch (err) {
      console.error(`   ❌ Error downloading ${f.name}:`, err.message);
    }
  }

  const manifestPath = path.join(OUTPUT_DIR, 'manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  console.log(`\n🎉 Download complete! Manifest saved to: ${manifestPath}`);
}

downloadAll().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
