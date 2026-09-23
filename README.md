# WScaner - WhatsApp OCR Scanner to Google Sheet

Bot WhatsApp cerdas untuk memindai foto majalah/buletin dakwah **Ulul Albab - Cerdas dan Mencerahkan**, mengekstrak metadata (Edisi, Tahun Romawi, Tanggal), 3 Judul Artikel, Penulis, dan Surah, lalu menyimpannya langsung ke **Google Sheet** secara otomatis.

Dilengkapi dengan arsitektur **4-Folder Bersih**, **5 Mesin OCR Fleksibel**, dan **Background Python Daemon** berlatensi rendah.

---

## 🌟 Fitur Utama

* **Arsitektur 4-Folder Bersih (`src/`, `data/`, `runtime/`, `scripts/`):** Struktur teratur dengan kedalaman maksimal 2 lapis, menjaga sesi WhatsApp tetap awet di `runtime/auth/`.
* **5 Pilihan Mesin OCR (Multi-Engine & Auto-Fallback):**
  1. **Groq Cloud Vision LLM (`qwen/qwen3.8-27b`)** — Inferensi LPU super cepat (~1.2 detik), 0 MB RAM, akurasi parsing 100% tanpa regex.
  2. **Google Gemini Vision LLM (`gemini-flash-latest`)** — Multimodal AI sangat cerdas menangani font artistik & nama majemuk.
  3. **Windows Native OCR (`Windows.Media.Ocr`)** — Sangat cepat (~350 ms), 100% offline lokal tanpa kuota/internet, konsumsi RAM hanya ~15 MB.
  4. **Google Drive Native OCR** — OCR bawaan Google Cloud Docs melalui konversi instan.
  5. **Auto / Hybrid Cascade** — Menguji lokal (Windows OCR) $\rightarrow$ otomatis fallback ke Groq VLM jika gambar miring/kurang lengkap $\rightarrow$ Gemini $\rightarrow$ Google Drive.
* **Persistent OCR Daemon:** Worker Python berjalan di latar belakang (port `5005`) sehingga pemindaian via WhatsApp merespons instan tanpa delay inisialisasi Python.
* **Onetimeused Media Extractor:** Mendukung penyimpanan foto sekali lihat (view-once) ke folder `data/downloads/`.
* **Integrasi Google Sheet:** Otomatis mengisi 9 kolom tabel dengan deteksi duplikasi data cover majalah.

---

## 📁 Struktur Proyek (Max 4-Folder Architecture)

```
WScaner/
│
├── 1. src/                       # Semua Source Code Aplikasi
│   ├── bot/                      # Node.js WhatsApp Bot (Baileys)
│   │   ├── bot.js                # Entry point bot
│   │   ├── config.js             # Konfigurasi path & environment
│   │   ├── whatsapp.js           # Siklus koneksi Baileys & QR Code
│   │   ├── messageHandler.js     # Logika pesan, perintah, & balasan WA
│   │   ├── ocrRunner.js          # Pemanggil daemon OCR & CLI fallback
│   │   ├── ocrDaemon.js          # Pengelola worker daemon Python
│   │   ├── sessionLogger.js      # Pencatat log aktivitas bot
│   │   ├── allowedNumbers.js     # Manajemen nomor telepon yang diizinkan
│   │   └── oneTimeUsed.js        # Ekstraktor foto sekali lihat
│   ├── ocr/                      # Modul Python OCR & Parsing
│   │   ├── server.py             # HTTP OCR daemon server (Port 5005)
│   │   ├── ocr_processor.py      # Core CLI & cascading fallback pipeline
│   │   ├── engine.py             # Windows Native OCR & Linux Tesseract
│   │   ├── groq_engine.py        # Groq Cloud Vision LLM (qwen3.8-27b)
│   │   ├── gemini_engine.py      # Google Gemini Vision LLM
│   │   ├── drive_engine.py       # Google Drive Docs Native OCR
│   │   ├── parser.py             # Regex & logika tata letak majalah
│   │   └── gas_client.py         # Pengirim HTTP payload ke Google Apps Script
│   └── gas/                      # Google Apps Script Source
│       ├── Kode.js               # Webhook doPost() & penulisan ke Google Sheet
│       └── appsscript.json       # Manifest runtime Google Apps Script
│
├── 2. data/                      # Dataset & Penyimpanan Berkas
│   ├── samples/                  # Cover majalah contoh pengujian (Example0-3)
│   ├── scans/                    # Pindaian terverifikasi & manifest.json
│   └── downloads/                # Folder tujuan unduhan foto sekali lihat
│
├── 3. runtime/                   # Sesi, Log & Cache Sementara (Diabaikan Git)
│   ├── auth/                     # Kredensial login Baileys WhatsApp
│   ├── logs/                     # Catatan log sesi bot
│   └── temp/                     # File sementara proses pindaian
│
└── 4. scripts/                   # Alat Bantu, Migrasi & Pengujian
    ├── downloadDriveScans.js     # Pengunduh arsip pindaian Google Drive
    ├── populate_sheet.py         # Skrip pengisi massal ke Google Sheets
    └── test_tuned_ocr.py         # Pengujian batch akurasi OCR pada dataset
```

---

## ⚙️ Konfigurasi Lingkungan (`.env`)

Salin file `.env.example` menjadi `.env`, lalu lengkapi kredensial:

```env
# Konfigurasi WhatsApp Bot
ALLOWED_NUMBER=628xxxxxxxxxx
START_COMMAND=#start
STOP_COMMAND=#stop
STATUS_COMMAND=#status
LOG_COMMAND=#log
LINK_COMMAND=#link
TUTO_COMMAND=#tuto

# Integrasi Google Spreadsheet & Apps Script
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/your-spreadsheet-id/edit
GAS_WEBHOOK_URL=https://script.google.com/macros/s/your-deployment-id/exec

# Pilihan Mesin Default: windows | groq | gemini | drive | auto
OCR_ENGINE=groq

# Kredensial Groq Cloud (Gratis)
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b

# Kredensial Google Gemini (Gratis)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-flash-latest

# Konfigurasi Daemon OCR
OCR_PORT=5005
```

---

## 🚀 Panduan Menjalankan

### Cara 1: Menggunakan File Batch (1-Click di Windows)

* **`start.bat`:** Menampilkan menu interaktif 5 pilihan mesin OCR dan langsung memulai bot WhatsApp.
* **`scan.bat`:** Menguji pindaian dokumen secara manual dari terminal:
  ```cmd
  scan.bat data/samples/Example0.jpg.jpeg --groq
  ```
* **`onetime.bat`:** Mengunduh foto sekali lihat ke `data/downloads/`.

---

### Cara 2: Menjalankan via Terminal (CLI)

1. **Jalankan Bot WhatsApp:**
   ```bash
   npm start
   ```
2. **Scan QR Code:**
   Jika baru pertama kali atau sesi terputus, pindai QR code yang tampil di terminal via WhatsApp (**Pengaturan > Perangkat Tertaut**).
3. **Kirim Perintah di WhatsApp:**
   * Ketik `#start` untuk mengaktifkan penerimaan foto.
   * Kirim foto majalah Ulul Albab — bot akan memproses dan mengembalikan ringkasan data serta link spreadsheet.

---

### Cara 3: Docker / Podman Container

Container telah dilengkapi dengan runtime Node.js, Python, dan persistensi volume untuk menjaga sesi WhatsApp login:

```bash
# Menggunakan Podman:
start-podman.bat

# Atau perintah standar Docker Compose:
npm run docker:up     # Jalankan di background
npm run docker:logs   # Lihat log & scan QR
npm run docker:down   # Matikan container
```

---

## ☁️ Deployment Google Apps Script (Clasp)

Google Apps Script berada di folder `src/gas/` dan dikonfigurasi melalui `.clasp.json`:

```bash
# Periksa status file yang dipantau
npx @google/clasp status

# Push kode ke Google Apps Script
npx @google/clasp push
```

---

## 🧪 Pengujian & Benchmarking

```bash
# Uji pindaian satu gambar contoh via Groq:
npm run test:ocr

# Uji akurasi batch pada seluruh dataset pindaian:
python scripts/test_tuned_ocr.py

# Kirim seluruh pindaian terverifikasi ke Google Sheets:
python scripts/populate_sheet.py
```
