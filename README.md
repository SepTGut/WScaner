# WScaner - WhatsApp OCR Scanner to Google Sheet

Bot WhatsApp otomatis untuk memindai foto majalah/buletin dakwah **Ulul Albab - Cerdas dan Mencerahkan**, mengekstrak metadata Edisi, Tanggal, 3 Judul Artikel, Penulis, dan Surah menggunakan OCR cerdas berkecepatan tinggi, lalu menyimpannya langsung ke **Google Sheet**.

Dapat dijalankan secara **Native di Windows** (menggunakan Windows Native OCR berkecepatan ~50ms) maupun di dalam **Docker** (menggunakan Tesseract OCR Linux).

---

## 📁 Struktur Folder Project

```
WScaner/
│
├── 📂 GAS/                      # Google Apps Script (dikelola via Clasp)
│   ├── Kode.js                  # Native doPost() & penulisan ke Google Sheet
│   └── appsscript.json          # Konfigurasi runtime Apps Script
│
├── 📂 ocr/                      # Modul Python (Engine OCR & Parsing)
│   ├── ocr_processor.py         # Entry point CLI pemrosesan OCR
│   ├── engine.py                # Dual engine: Windows Native OCR & Linux Tesseract
│   ├── parser.py                # Algoritma 2-gap, ekstraksi Edisi, Penulis, & Surah
│   └── gas_client.py            # Pengiriman HTTP POST payload ke Google Sheet
│
├── 📂 src/                      # Modul Node.js (WhatsApp Bot)
│   ├── bot.js                   # Entry point bot WhatsApp
│   ├── config.js                # Pengelolaan variabel lingkungan (.env)
│   ├── whatsapp.js              # Siklus koneksi Baileys & tampilan QR Code
│   ├── messageHandler.js        # Filter nomor, perintah #start/#stop, & balasan WA
│   └── ocrRunner.js             # Eksekusi ocr_processor.py secara asynchronous
│
├── 📂 Data/                     # File contoh gambar untuk pengujian
├── start.bat                    # Klik 2x untuk menjalankan bot di Windows
├── Dockerfile                   # Build multi-runtime (Node + Python + Tesseract)
├── docker-compose.yml           # Persistensi volume WhatsApp login & temp files
├── requirements.txt             # Dependensi Python
├── package.json                 # Dependensi Node.js & npm scripts
├── .env.example                 # Template konfigurasi
└── .env                         # Konfigurasi kredensial aktif
```

---

## ⚙️ Konfigurasi (`.env`)

Isi file `.env` dengan nomor WhatsApp Anda:
```env
ALLOWED_NUMBER=628xxxxxxxxxx
START_COMMAND=#start
STOP_COMMAND=#stop
STATUS_COMMAND=#status
GAS_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
```

---

## 🚀 Cara Menjalankan

### Opsi 1: NATIVE (Windows — Direkomendasikan untuk akurasi & kecepatan tertinggi)
1. Cukup klik ganda file [**`start.bat`**](file:///d:/MyCode/WScaner/start.bat), atau ketik:
   ```bash
   npm start
   ```
2. Scan QR Code yang muncul di terminal menggunakan WhatsApp di HP Anda (**Perangkat Tertaut > Tautkan Perangkat**).
3. Kirim **`#start`** di chat WhatsApp.
4. Kirim foto majalah Ulul Albab — data akan langsung masuk ke Google Sheet!

---

### Opsi 2: DOCKER / PODMAN (Container Service)
Jika menggunakan **Podman** (rekomendasi pengganti Docker):
```bash
# Pastikan machine podman sudah berjalan:
podman machine start

# Jalankan via npm script:
npm run podman:up     # Jalankan container di latar belakang
npm run podman:logs   # Tampilkan QR code & logs
npm run podman:down   # Hentikan container

# Atau langsung klik ganda file start-podman.bat
```

Jika masih menggunakan **Docker**:
```bash
npm run docker:up     # Jalankan container di latar belakang
npm run docker:logs   # Tampilkan QR code & logs
npm run docker:down   # Hentikan container
```

---

## 🧪 Uji Coba Cepat (Test OCR)
```bash
npm run test:ocr
```
