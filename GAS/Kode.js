const DATA_START_ROW = 6;

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

function getOrCreateFolder(folderName) {
  const folders = DriveApp.getFoldersByName(folderName);
  if (folders.hasNext()) {
    return folders.next();
  }
  return DriveApp.createFolder(folderName);
}

function getNextRow(sheet) {
  const lastRow = sheet.getLastRow();
  return Math.max(DATA_START_ROW, lastRow + 1);
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
    const edition = data.edition || "";
    
    // Save photo to Google Drive folder "DB-WScan" if provided
    let fileUrl = "";
    if (data.image_base64) {
      try {
        const folder = getOrCreateFolder("DB-WScan");
        const decoded = Utilities.base64Decode(data.image_base64);
        const fileName = data.image_name || ("scan_" + (edition ? "Ed" + edition + "_" : "") + Date.now() + ".jpg");
        const blob = Utilities.newBlob(decoded, data.image_mime || "image/jpeg", fileName);
        const file = folder.createFile(blob);
        file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
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
          nextNo,
          timestamp,
          date,
          edition,
          art.title || "",
          art.author || "",
          art.surah || "-",
          photoHyperlink
        ];
      });
      sheet.getRange(startRow, 1, rows.length, 8).setValues(rows);
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
  
  // Use semicolon (;) for Indonesian Google Sheets formula
  const photoFormula = `=HYPERLINK("${testUrl}"; "[Link]")`;

  sheet.getRange(targetRow, 1, 1, 8).setValues([[
    nextNo,
    Utilities.formatDate(new Date(), "GMT+7", "yyyy-MM-dd HH:mm"),
    "April 2026",
    "99 (TEST)",
    "Uji Coba Native Interaksi Sheet + Drive",
    "WScaner Bot",
    "-",
    photoFormula
  ]]);
  
  Logger.log("✅ Test row & Drive file added successfully to Row " + targetRow + " (No " + nextNo + "): " + testUrl);
}
