const DATA_START_ROW = 5;

function getTargetSheet() {
  var ss = null;
  try {
    ss = SpreadsheetApp.getActiveSpreadsheet();
  } catch (e) {}
  if (!ss) {
    // Fallback for standalone web app execution
    ss = SpreadsheetApp.openById("1fcBQJNoGU6bO1RcXEMiNCW5UB450VHmLTMtWPfDumFw");
  }
  return ss.getActiveSheet() || ss.getSheets()[0];
}

const TARGET_DB_FOLDER_ID = "15ytN9NDqTkmpW5qLt3nVGF2A9qj3Wjhe";
var CACHED_FOLDER = null;

function getOrCreateFolder(folderName) {
  if (CACHED_FOLDER) {
    return CACHED_FOLDER;
  }
  try {
    CACHED_FOLDER = DriveApp.getFolderById(TARGET_DB_FOLDER_ID);
    return CACHED_FOLDER;
  } catch (idErr) {
    const folders = DriveApp.getFoldersByName(folderName || "DB-WScan");
    if (folders.hasNext()) {
      CACHED_FOLDER = folders.next();
      return CACHED_FOLDER;
    }
    CACHED_FOLDER = DriveApp.createFolder(folderName || "DB-WScan");
    return CACHED_FOLDER;
  }
}

function getNextRow(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) {
    return DATA_START_ROW;
  }
  // Inspect Column A to find the last filled data row
  const colA = sheet.getRange(DATA_START_ROW, 1, Math.max(1, lastRow - DATA_START_ROW + 1), 1).getValues();
  for (let i = colA.length - 1; i >= 0; i--) {
    if (colA[i][0] !== "" && colA[i][0] !== null && colA[i][0] !== undefined) {
      return DATA_START_ROW + i + 1;
    }
  }
  return DATA_START_ROW;
}

function doGet(e) {
  if (e && e.parameter && e.parameter.action === "inspect_drive") {
    const targetId = e.parameter.folder_id || "15ytN9NDqTkmpW5qLt3nVGF2A9qj3Wjhe";
    return ContentService.createTextOutput(JSON.stringify(inspectDriveAccess(targetId))).setMimeType(ContentService.MimeType.JSON);
  }
  if (e && e.parameter && (e.parameter.action === "list_drive" || e.parameter.action === "check_drive")) {
    const fId = e.parameter.folder_id || e.parameter.folderId || null;
    return ContentService.createTextOutput(JSON.stringify(listDriveFiles(fId))).setMimeType(ContentService.MimeType.JSON);
  }
  return ContentService.createTextOutput(JSON.stringify({
    status: "ok",
    message: "WScaner Web App is running",
    timestamp: Utilities.formatDate(new Date(), "GMT+7", "yyyy-MM-dd HH:mm:ss")
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "No post data received"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    const sheet = getTargetSheet();
    const data = JSON.parse(e.postData.contents);

    // Support listing files in DB-WScan Google Drive folder or custom folder_id
    if (data.action === "list_drive" || data.action === "get_drive_files" || data.action === "check_drive") {
      const fId = data.folder_id || data.folderId || null;
      const driveRes = listDriveFiles(fId);
      return ContentService.createTextOutput(JSON.stringify(driveRes)).setMimeType(ContentService.MimeType.JSON);
    }

    // Support downloading file as base64 from Drive
    if (data.action === "get_file_base64" || data.action === "download_file") {
      const fileRes = getDriveFileBase64(data.file_id || data.fileId);
      return ContentService.createTextOutput(JSON.stringify(fileRes)).setMimeType(ContentService.MimeType.JSON);
    }

    // Support clearing sheet data (Rows 5+, Cols 1-9)
    if (data.action === "clear" || data.action === "clear_data" || data.action === "clear_sheet") {
      const clearRes = clearSheetData();
      return ContentService.createTextOutput(JSON.stringify(clearRes)).setMimeType(ContentService.MimeType.JSON);
    }

    // Support Google Drive Native OCR
    if (data.action === "ocr_drive" || data.action === "drive_ocr") {
      const ocrRes = performDriveOcr(data.file_id || data.fileId, data.image_base64, data.image_mime);
      return ContentService.createTextOutput(JSON.stringify(ocrRes)).setMimeType(ContentService.MimeType.JSON);
    }
    
    const timestamp = data.timestamp || Utilities.formatDate(new Date(), "GMT+7", "yyyy-MM-dd HH:mm");
    const date = data.date || "April 2026";
    const tahun = data.year_roman || "-";
    const edition = data.edition || "-";
    
    // Use existing Drive URL or save photo to Google Drive folder "DB-WScan" if provided
    let fileUrl = data.file_url || data.fileUrl || data.url || "";
    if (!fileUrl && data.image_base64) {
      try {
        const folder = getOrCreateFolder("DB-WScan");
        const decoded = Utilities.base64Decode(data.image_base64);
        const fileName = data.image_name || ("scan_" + (edition !== "-" ? "Ed" + edition + "_" : "") + Date.now() + ".jpg");
        const blob = Utilities.newBlob(decoded, data.image_mime || "image/jpeg", fileName);
        const file = folder.createFile(blob);
        fileUrl = file.getUrl();
      } catch (driveErr) {
        Logger.log("Drive save error: " + driveErr.toString());
      }
    }

    // Default to semicolon (;) for Indonesian Google Sheets formula
    const photoHyperlink = fileUrl ? `=HYPERLINK("${fileUrl}"; "[Link]")` : "-";

    if (data.articles && data.articles.length > 0) {
      const startRow = getNextRow(sheet);
      const rows = data.articles.map(function(art, idx) {
        const currentRow = startRow + idx;
        const nextNo = currentRow - DATA_START_ROW + 1;
        return [
          nextNo,             // Col 1 (A): No
          timestamp,          // Col 2 (B): TimeStamp
          date,               // Col 3 (C): Date
          tahun,              // Col 4 (D): Tahun (Angka Romawi)
          edition,            // Col 5 (E): Edition
          art.title || "",    // Col 6 (F): Article
          art.author || "",   // Col 7 (G): Author
          art.surah || "-",   // Col 8 (H): Surah
          photoHyperlink      // Col 9 (I): LInk Foto 
        ];
      });

      // Write exactly 9 columns (leaving Col 10 'JANGAN DIRUBAH' untouched)
      const dataRange = sheet.getRange(startRow, 1, rows.length, 9);
      dataRange.setValues(rows);

      // Fast single-pass formatting
      dataRange.setVerticalAlignment("middle");
      const alignments = rows.map(function() {
        return ["center", "center", "center", "center", "center", "left", "left", "center", "center"];
      });
      dataRange.setHorizontalAlignments(alignments);
      sheet.getRange(startRow, 6, rows.length, 2).setWrap(true);
    }

    return ContentService.createTextOutput(JSON.stringify({ 
      status: "success", 
      message: "Data appended natively to sheet",
      articles_added: data.articles ? data.articles.length : 0,
      drive_file_url: fileUrl || null
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ 
      status: "error", 
      message: err.toString() 
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function testNativeWrite() {
  const sheet = getTargetSheet();
  const targetRow = getNextRow(sheet);
  const nextNo = targetRow - DATA_START_ROW + 1;
  
  // Test folder creation in Drive
  const folder = getOrCreateFolder("DB-WScan");
  const testBlob = Utilities.newBlob("Uji coba file WScaner Drive", "text/plain", "test_" + Date.now() + ".txt");
  const file = folder.createFile(testBlob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  const testUrl = file.getUrl();
  
  const photoFormula = `=HYPERLINK("${testUrl}"; "[Link]")`;

  const dataRange = sheet.getRange(targetRow, 1, 1, 9);
  dataRange.setValues([[
    nextNo,
    Utilities.formatDate(new Date(), "GMT+7", "yyyy-MM-dd HH:mm"),
    "April 2026",
    "XI",
    "50",
    "Uji Coba Native Interaksi Sheet + Drive",
    "WScaner Bot",
    "-",
    photoFormula
  ]]);
  
  dataRange.setVerticalAlignment("middle");
  sheet.getRange(targetRow, 1, 1, 5).setHorizontalAlignment("center");
  sheet.getRange(targetRow, 6, 1, 2).setHorizontalAlignment("left").setWrap(true);
  sheet.getRange(targetRow, 8, 1, 2).setHorizontalAlignment("center");
  
  Logger.log("✅ Test row & Drive file added successfully to Row " + targetRow + " (No " + nextNo + "): " + testUrl);
}

function clearSheetData() {
  const sheet = getTargetSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow >= DATA_START_ROW) {
    const numRows = lastRow - DATA_START_ROW + 1;
    // Clear only columns 1 to 9 (A:I), keeping Column 10 (J: JANGAN DIRUBAH) and Header rows 1-4 intact
    sheet.getRange(DATA_START_ROW, 1, numRows, 9).clearContent();
    Logger.log("✅ Berhasil mengosongkan data baris " + DATA_START_ROW + " sampai " + lastRow + " (Total: " + numRows + " baris)");
    return {
      status: "success",
      message: "Data rows successfully cleared",
      cleared_rows: numRows
    };
  }
  Logger.log("ℹ️ Tidak ada data baris yang perlu dikosongkan.");
  return {
    status: "success",
    message: "No data rows to clear",
    cleared_rows: 0
  };
}

function listDriveFiles(folderId) {
  try {
    const folderList = [];
    const allFiles = [];

    function processFolder(folder) {
      folderList.push({
        id: folder.getId(),
        name: folder.getName(),
        url: folder.getUrl()
      });

      const files = folder.getFiles();
      while (files.hasNext()) {
        const f = files.next();
        allFiles.push({
          folderId: folder.getId(),
          folderName: folder.getName(),
          id: f.getId(),
          name: f.getName(),
          mimeType: f.getMimeType(),
          sizeBytes: f.getSize(),
          sizeKb: (f.getSize() / 1024).toFixed(1) + " KB",
          created: Utilities.formatDate(f.getDateCreated(), "GMT+7", "yyyy-MM-dd HH:mm:ss"),
          lastUpdated: Utilities.formatDate(f.getLastUpdated(), "GMT+7", "yyyy-MM-dd HH:mm:ss"),
          url: f.getUrl()
        });
      }
    }

    if (folderId) {
      const folder = DriveApp.getFolderById(folderId);
      processFolder(folder);
    } else {
      const folders = DriveApp.getFoldersByName("DB-WScan");
      while (folders.hasNext()) {
        processFolder(folders.next());
      }
    }

    allFiles.sort(function(a, b) {
      return b.created.localeCompare(a.created);
    });

    return {
      status: "success",
      folders: folderList,
      total_files: allFiles.length,
      files: allFiles
    };
  } catch (err) {
    return {
      status: "error",
      message: err.toString()
    };
  }
}

function inspectDriveAccess(targetId) {
  const result = {
    targetId: targetId,
    rootFolder: null,
    spreadsheetParents: [],
    searchById: null,
    matchingFolders: [],
    recentFolders: []
  };

  try {
    const root = DriveApp.getRootFolder();
    result.rootFolder = { name: root.getName(), id: root.getId() };
  } catch (e) {
    result.rootFolder = e.toString();
  }

  try {
    const ssFile = DriveApp.getFileById("1fcBQJNoGU6bO1RcXEMiNCW5UB450VHmLTMtWPfDumFw");
    const parents = ssFile.getParents();
    while (parents.hasNext()) {
      const p = parents.next();
      result.spreadsheetParents.push({ name: p.getName(), id: p.getId() });
    }
  } catch (e) {
    result.spreadsheetParents = e.toString();
  }

  try {
    const f = DriveApp.getFolderById(targetId);
    result.searchById = { name: f.getName(), id: f.getId(), url: f.getUrl() };
  } catch (e) {
    result.searchById = e.toString();
  }

  try {
    const searched = DriveApp.searchFolders('title contains "DB" or title contains "Scan" or title contains "WScan"');
    while (searched.hasNext()) {
      const sf = searched.next();
      result.matchingFolders.push({ name: sf.getName(), id: sf.getId() });
    }
  } catch (e) {
    result.matchingFolders = e.toString();
  }

  try {
    const trashed = DriveApp.getTrashedFolders();
    while (trashed.hasNext()) {
      const tf = trashed.next();
      if (tf.getId() === targetId) {
        result.searchById = { status: "trashed", name: tf.getName(), id: tf.getId() };
      }
    }
  } catch (e) {}

  return result;
}

function getDriveFileBase64(fileId) {
  try {
    const file = DriveApp.getFileById(fileId);
    return {
      status: "success",
      id: file.getId(),
      name: file.getName(),
      mimeType: file.getMimeType(),
      sizeBytes: file.getSize(),
      base64: Utilities.base64Encode(file.getBlob().getBytes())
    };
  } catch (err) {
    return {
      status: "error",
      message: err.toString()
    };
  }
}

function performDriveOcr(fileId, imageBase64, imageMime) {
  let targetFileId = fileId;
  let createdTempFile = false;

  try {
    if (!targetFileId && imageBase64) {
      const folder = getOrCreateFolder("DB-WScan");
      const decoded = Utilities.base64Decode(imageBase64);
      const blob = Utilities.newBlob(decoded, imageMime || "image/jpeg", "temp_ocr_" + Date.now() + ".jpg");
      const tempFile = folder.createFile(blob);
      targetFileId = tempFile.getId();
      createdTempFile = true;
    }

    if (!targetFileId) {
      return { status: "error", message: "file_id or image_base64 is required" };
    }

    // Call Drive REST API v2 to copy image into a Google Doc with OCR enabled
    const token = ScriptApp.getOAuthToken();
    const copyUrl = "https://www.googleapis.com/drive/v2/files/" + encodeURIComponent(targetFileId) + "/copy?ocr=true&ocrLanguage=id";
    const copyPayload = JSON.stringify({
      title: "tmp_ocr_doc_" + Date.now(),
      mimeType: "application/vnd.google-apps.document"
    });

    const copyRes = UrlFetchApp.fetch(copyUrl, {
      method: "post",
      headers: {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json"
      },
      payload: copyPayload,
      muteHttpExceptions: true
    });

    const copyCode = copyRes.getResponseCode();
    if (copyCode < 200 || copyCode >= 300) {
      return { status: "error", code: copyCode, message: "Drive OCR copy failed: " + copyRes.getContentText() };
    }

    const docMeta = JSON.parse(copyRes.getContentText());
    const docId = docMeta.id;

    // Read the text from the created Google Doc
    let extractedText = "";
    try {
      const doc = DocumentApp.openById(docId);
      extractedText = doc.getBody().getText();
    } catch (docErr) {
      if (docMeta.exportLinks && docMeta.exportLinks["text/plain"]) {
        const textRes = UrlFetchApp.fetch(docMeta.exportLinks["text/plain"], {
          headers: { "Authorization": "Bearer " + token },
          muteHttpExceptions: true
        });
        extractedText = textRes.getContentText();
      } else {
        throw docErr;
      }
    }

    // Delete the temporary Google Doc
    try {
      DriveApp.getFileById(docId).setTrashed(true);
    } catch (trashErr) {
      Logger.log("Trash temp doc error: " + trashErr.toString());
    }

    const lines = extractedText.split("\n")
      .map(function(l) { return l.trim(); })
      .filter(function(l) { return l.length > 0; });

    return {
      status: "success",
      source: "Google Drive Built-in OCR",
      file_id: targetFileId,
      raw_text: extractedText,
      lines: lines
    };
  } catch (err) {
    return { status: "error", message: err.toString() };
  }
}
