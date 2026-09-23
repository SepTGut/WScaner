# Graph Report - WScaner  (2026-09-23)

## Corpus Check
- Large corpus: 49 files · ~690,541 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 247 nodes · 430 edges · 15 communities (13 shown, 2 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 64 edges (avg confidence: 0.9)
- Token cost: 1,250 input · 850 output

## Community Hubs (Navigation)
- OCR Engine & Parser
- WhatsApp Message Dispatcher
- Node.js Package Manifest
- Phone Whitelist & Access Control
- OCR Microservice HTTP Server
- One-Time Image Processor
- WhatsApp Bot Lifecycle & Daemon
- Google Apps Script Backend
- GAS Scopes & Manifest
- Session Logger & Rotator
- Google Drive Scan Downloader
- Container & Deployment Specs
- Bot Environment Configuration
- Spreadsheet Data Tools

## God Nodes (most connected - your core abstractions)
1. `handleMessage()` - 16 edges
2. `Google Apps Script Sheets Sync` - 16 edges
3. `process_image()` - 14 edges
4. `OCR Inference & Parsing Pipeline` - 13 edges
5. `scripts` - 12 edges
6. `doPost()` - 9 edges
7. `normalizePhone()` - 8 edges
8. `get_ocr_engine_name()` - 8 edges
9. `parse_metadata()` - 8 edges
10. `parse_articles()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `WhatsApp Baileys Bot Service` --references--> `{ initWhatsAppBot }`  [INFERRED]
  README.md → src/bot/bot.js
- `WhatsApp Baileys Bot Service` --references--> `ocrDaemon`  [INFERRED]
  README.md → src/bot/bot.js
- `WhatsApp Baileys Bot Service` --references--> `engineName`  [INFERRED]
  README.md → src/bot/bot.js
- `Google Apps Script Sheets Sync` --references--> `processFolder()`  [INFERRED]
  README.md → src/gas/Kode.js
- `Sample Receipts Image Dataset` --shares_data_with--> `OCR Inference & Parsing Pipeline`  [INFERRED]
  data/samples/Data0-2.jpg.jpeg → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **WScaner Ingestion Triad** — readme_whatsapp_bot_service, readme_ocr_inference_pipeline, readme_google_apps_script_sync [INFERRED 0.85]

## Communities (15 total, 2 thin omitted)

### Community 0 - "OCR Engine & Parser"
Cohesion: 0.08
Nodes (38): populate(), test_all(), extract_with_drive(), get_google_access_token(), parse_drive_ocr_lines(), Parses metadata and 3 sidebar articles from Google Drive plain text OCR output., Retrieves and auto-refreshes Google OAuth2 access token. Checks ~/.clasprc.json…, Main entry point for Google Drive Native OCR. Executes cloud OCR via Drive API,… (+30 more)

### Community 1 - "WhatsApp Message Dispatcher"
Cohesion: 0.09
Nodes (30): allowedNumbers, botSentMessageIds, config, { downloadMediaMessage, jidNormalizedUser }, enqueueGASUpload(), formatSuccessReply(), fs, gasQueue (+22 more)

### Community 2 - "Node.js Package Manifest"
Cohesion: 0.07
Nodes (29): axios, dotenv, heic-convert, dependencies, axios, dotenv, heic-convert, pino (+21 more)

### Community 3 - "Phone Whitelist & Access Control"
Cohesion: 0.16
Nodes (24): addNumber(), config, fs, getAllowedNumbers(), isNumberAllowed(), loadAllowedNumbers(), normalizePhone(), NUMBERS_FILE (+16 more)

### Community 4 - "OCR Microservice HTTP Server"
Cohesion: 0.19
Nodes (16): BaseHTTPRequestHandler, Sample Receipts Image Dataset, HTTPServer, WScaner Architecture Overview, OCR Inference & Parsing Pipeline, Pillow Image Processing, PyTesseract OCR Library, Windows Native OCR Library (+8 more)

### Community 5 - "One-Time Image Processor"
Cohesion: 0.15
Nodes (20): allowedNumbers, config, {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  downloadMediaMessage,
  jidNormalizedUser
}, determineFileExtension(), extractImageInfo(), fs, IGNORED_LIBSIGNAL_LOGS, IPHONE_IMAGE_EXTENSIONS (+12 more)

### Community 6 - "WhatsApp Bot Lifecycle & Daemon"
Cohesion: 0.15
Nodes (12): WhatsApp Baileys Bot Service, engineName, { initWhatsAppBot }, ocrDaemon, path, ROOT_DIR, axios, checkHealth() (+4 more)

### Community 7 - "Google Apps Script Backend"
Cohesion: 0.34
Nodes (15): Batch Scanned Invoices Dataset, Google Apps Script Sheets Sync, Requests HTTP Library, clearSheetData(), doGet(), doPost(), getDriveFileBase64(), getNextRow() (+7 more)

### Community 8 - "GAS Scopes & Manifest"
Cohesion: 0.15
Nodes (12): https://www.googleapis.com/auth/documents, https://www.googleapis.com/auth/drive, https://www.googleapis.com/auth/script.external_request, https://www.googleapis.com/auth/spreadsheets, dependencies, exceptionLogging, oauthScopes, runtimeVersion (+4 more)

### Community 9 - "Session Logger & Rotator"
Cohesion: 0.33
Nodes (9): cleanOldLogs(), config, endSession(), ensureLogsDir(), fs, getLatestLogFile(), logToSession(), path (+1 more)

### Community 10 - "Google Drive Scan Downloader"
Cohesion: 0.33
Nodes (4): axios, fs, OUTPUT_DIR, path

### Community 11 - "Container & Deployment Specs"
Cohesion: 0.67
Nodes (3): Persistent Volume Mounts, Docker Compose WScaner Service, Containerized Deployment

## Knowledge Gaps
- **86 isolated node(s):** `name`, `version`, `description`, `main`, `start` (+81 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `WScaner Architecture Overview` connect `OCR Microservice HTTP Server` to `WhatsApp Bot Lifecycle & Daemon`, `Google Apps Script Backend`?**
  _High betweenness centrality (0.336) - this node is a cross-community bridge._
- **Why does `WhatsApp Baileys Bot Service` connect `WhatsApp Bot Lifecycle & Daemon` to `OCR Microservice HTTP Server`?**
  _High betweenness centrality (0.300) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `Google Apps Script Sheets Sync` (e.g. with `Batch Scanned Invoices Dataset` and `Kode.js`) actually correct?**
  _`Google Apps Script Sheets Sync` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `OCR Inference & Parsing Pipeline` (e.g. with `Sample Receipts Image Dataset` and `server.py`) actually correct?**
  _`OCR Inference & Parsing Pipeline` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `version`, `description` to the rest of the system?**
  _86 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `OCR Engine & Parser` be split into smaller, more focused modules?**
  _Cohesion score 0.08067375886524823 - nodes in this community are weakly interconnected._
- **Should `WhatsApp Message Dispatcher` be split into smaller, more focused modules?**
  _Cohesion score 0.0907258064516129 - nodes in this community are weakly interconnected._