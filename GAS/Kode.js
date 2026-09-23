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

var CACHED_FOLDER = null;

function getOrCreateFolder(folderName) {
  if (CACHED_FOLDER) {
    return CACHED_FOLDER;
  }
  const folders = DriveApp.getFoldersByName(folderName);
  if (folders.hasNext()) {
    CACHED_FOLDER = folders.next();
    return CACHED_FOLDER;
  }
  CACHED_FOLDER = DriveApp.createFolder(folderName);
  return CACHED_FOLDER;
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
    
    const timestamp = data.timestamp || Utilities.formatDate(new Date(), "GMT+7", "yyyy-MM-dd HH:mm");
    const date = data.date || "April 2026";
    const tahun = data.year_roman || "-";
    const edition = data.edition || "-";
    
    // Save photo to Google Drive folder "DB-WScan" if provided
    let fileUrl = "";
    if (data.image_base64) {
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
