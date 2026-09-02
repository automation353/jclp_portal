/**
 * "Capture once, remember forever" column-mirroring for two report types.
 *
 * SHEETS
 *   DPR flow: stock_valuation -> stock_valuation_columns
 *                                (subset of highlighted columns; wiped + rewritten each upload)
 *             stock_valuation_columns -> combined
 *                                (accumulating append-only history)
 *   PO  flow: po -> po_highlighted_columns
 *                                (subset of highlighted columns; wiped + rewritten each upload)
 *
 * WHY THIS SHAPE
 *   stock_valuation (and PO) get wiped and re-written on every upload, so any
 *   highlight fill in those tabs will be lost. Instead we capture the
 *   highlighted header column NAMES once, save them to document properties,
 *   and on every future run we look those names up in whatever new header
 *   row exists.
 *
 * ONE-TIME SETUP
 *   1. Extensions -> Apps Script. Paste this whole file. Save.
 *   2. DPR: while stock_valuation has the desired columns highlighted, pick
 *      `captureHighlightedColumnNames` from the function dropdown and Run.
 *      PO:  while PO has the desired columns highlighted, pick
 *      `captureHighlightedColumnNamesPO` and Run.
 *      Authorize when prompted. Check the Execution log — each should print
 *      the list of captured names.
 *   3. Deploy -> New deployment -> Web app.
 *        Execute as: Me. Access: Anyone.
 *      Copy the Web app URL.
 *   4. Paste that same URL into TWO places in n8n:
 *        DPR workflow (Sync stock_valuation_columns via Apps Script node): as-is
 *        PO  workflow (Sync po_highlighted_columns via Apps Script node):  append `?type=po`
 *      e.g. `https://script.google.com/…/exec?type=po`
 *      The `type` query parameter is what routes each call to the right sync.
 *
 * ROUTING
 *   No query parameter (or type=dpr) -> stock_valuation -> stock_valuation_columns
 *                                       (+ combined append).
 *   type=po                          -> po -> po_highlighted_columns.
 *
 * IF YOU CHANGE WHICH COLUMNS ARE HIGHLIGHTED
 *   Re-run the matching capture function — it overwrites the saved list.
 *   Or run `clearCapturedColumnNames` / `clearCapturedColumnNamesPO` to reset.
 */

// -------- DPR flow config --------
var SOURCE_SHEET_NAME  = 'stock_valuation';
var TARGET_SHEET_NAME  = 'stock_valuation_columns';
// `combined` is now the RM dashboard tab (populated by formulas). The DPR-PO
// append-only history goes to its own tab so the dashboard is never touched
// by this script.
var MIRROR_SHEET_NAME  = 'dpr_po_joined';
var PROP_KEY           = 'HIGHLIGHTED_COLUMN_NAMES';

// -------- PO flow config --------
var PO_SOURCE_SHEET_NAME = 'po';
var PO_TARGET_SHEET_NAME = 'po_highlighted_columns';
var PO_PROP_KEY          = 'PO_HIGHLIGHTED_COLUMN_NAMES';

// ============================================================================
// HTTP entry points — the same Web app URL handles both flows via ?type=...
// ============================================================================

function doPost(e) { return routeRequest_(e); }
function doGet(e)  { return routeRequest_(e); }

function routeRequest_(e) {
  var type = (e && e.parameter && e.parameter.type) ? String(e.parameter.type).toLowerCase() : 'dpr';
  if (type === 'po') {
    return respondJson_(function () { return syncCapturedColumnsToPOHighlighted(); });
  }
  return respondJson_(function () { return syncStockValuationColumns(); });
}

function respondJson_(fn) {
  try {
    var result = fn();
    return ContentService
      .createTextOutput(JSON.stringify(Object.assign({ status: 'success' }, result)))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'error', message: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ============================================================================
// Generic helpers — both flows share this logic. Parameterised on which sheet
// to read from, which sheet to write to, and which properties key to use.
// ============================================================================

function normalizeHeader_(text) {
  return String(text || '')
    .replace(/\r/g, ' ')
    .replace(/\n/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Forgiving tab lookup: exact match first, then case-insensitive + trimmed.
 * If not found, throws a clear error listing every tab that actually exists,
 * so mismatches (typos, extra spaces, wrong capitalization) are obvious.
 */
function resolveSheet_(ss, wantedName) {
  var exact = ss.getSheetByName(wantedName);
  if (exact) return exact;

  var wantedNorm = String(wantedName || '').replace(/\s+/g, ' ').trim().toLowerCase();
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    var actual = sheets[i].getName();
    var actualNorm = String(actual).replace(/\s+/g, ' ').trim().toLowerCase();
    if (actualNorm === wantedNorm) return sheets[i];
  }

  var actualNames = sheets.map(function (s) { return '"' + s.getName() + '"'; });
  throw new Error(
    'Sheet "' + wantedName + '" not found in this spreadsheet. ' +
    'Tabs that actually exist: [' + actualNames.join(', ') + ']. ' +
    'Check the exact spelling (capitalization, spaces vs underscores).'
  );
}

/**
 * DIAGNOSTIC — logs every tab name in the bound spreadsheet plus which
 * spreadsheet the script is attached to. Run this from the Apps Script
 * editor if a "Sheet not found" error is happening — the output will show
 * both what the script sees and what you expect.
 */
function listTabs() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var report = {
    spreadsheetName: ss.getName(),
    spreadsheetUrl:  ss.getUrl(),
    tabs: ss.getSheets().map(function (s) { return s.getName(); })
  };
  Logger.log(JSON.stringify(report, null, 2));
  return report;
}

function captureHighlightedNames_(sourceSheetName, propKey) {
  var ss  = SpreadsheetApp.getActiveSpreadsheet();
  var src = resolveSheet_(ss, sourceSheetName);

  var lastCol = src.getLastColumn();
  if (lastCol < 1) throw new Error(sourceSheetName + ' has no columns.');

  var headerRange = src.getRange(1, 1, 1, lastCol);
  var backgrounds = headerRange.getBackgrounds()[0];
  var headers     = headerRange.getValues()[0];

  var names = [];
  for (var i = 0; i < backgrounds.length; i++) {
    var color = (backgrounds[i] || '').toLowerCase();
    if (color === '' || color === '#ffffff') continue;
    var name = normalizeHeader_(headers[i]);
    if (name) names.push(name);
  }

  if (names.length === 0) {
    throw new Error('No highlighted columns found in ' + sourceSheetName + '. Highlight the desired header cells with a fill color first.');
  }

  PropertiesService.getDocumentProperties().setProperty(propKey, JSON.stringify(names));
  Logger.log('[' + sourceSheetName + '] Captured ' + names.length + ' column names: ' + names.join(', '));
  return { capturedCount: names.length, columnNames: names };
}

function getCapturedNames_(propKey) {
  var raw = PropertiesService.getDocumentProperties().getProperty(propKey);
  if (!raw) return null;
  try {
    var arr = JSON.parse(raw);
    return Array.isArray(arr) && arr.length > 0 ? arr : null;
  } catch (e) {
    return null;
  }
}

function clearCapturedNames_(propKey) {
  PropertiesService.getDocumentProperties().deleteProperty(propKey);
  Logger.log('Cleared saved column names for property key: ' + propKey);
}

/**
 * Given a source tab and a saved list of column names, wipe the target tab
 * and write header + matching data rows. Returns row/column counts and any
 * saved names that were not found in the current source header row.
 *
 * Also returns `outRows` so the caller can do further work with the data
 * (e.g. the DPR flow appends it into the combined history tab).
 */
function syncBySavedNames_(sourceSheetName, targetSheetName, savedNames) {
  var ss  = SpreadsheetApp.getActiveSpreadsheet();
  var src = resolveSheet_(ss, sourceSheetName);
  var tgt = resolveSheet_(ss, targetSheetName);

  var lastRow = src.getLastRow();
  var lastCol = src.getLastColumn();
  if (lastRow < 1 || lastCol < 1) throw new Error(sourceSheetName + ' appears to be empty.');

  var currentHeaders = src.getRange(1, 1, 1, lastCol).getValues()[0].map(normalizeHeader_);
  var headerIndex = {};
  for (var i = 0; i < currentHeaders.length; i++) {
    var h = currentHeaders[i];
    if (h && !(h in headerIndex)) headerIndex[h] = i;
  }

  var chosenIndexes = [];
  var missing = [];
  for (var k = 0; k < savedNames.length; k++) {
    var name = savedNames[k];
    if (name in headerIndex) chosenIndexes.push(headerIndex[name]);
    else missing.push(name);
  }

  if (chosenIndexes.length === 0) {
    throw new Error('None of the saved column names were found in the current ' + sourceSheetName + ' header. Saved: ' + savedNames.join(', '));
  }

  var body = src.getRange(2, 1, Math.max(lastRow - 1, 0), lastCol).getValues();
  var outRows = [savedNames.filter(function (n) { return missing.indexOf(n) < 0; })];
  for (var r = 0; r < body.length; r++) {
    outRows.push(chosenIndexes.map(function (idx) { return body[r][idx]; }));
  }

  tgt.clearContents();
  tgt.getRange(1, 1, outRows.length, outRows[0].length).setValues(outRows);

  return {
    columnsCopied: chosenIndexes.length,
    rowsCopied: outRows.length - 1,
    missingSavedColumns: missing,
    outRows: outRows
  };
}

// ============================================================================
// DPR flow: stock_valuation -> stock_valuation_columns (+ combined append).
// ============================================================================

function captureHighlightedColumnNames() {
  return captureHighlightedNames_(SOURCE_SHEET_NAME, PROP_KEY);
}

function clearCapturedColumnNames() {
  clearCapturedNames_(PROP_KEY);
}

function syncStockValuationColumns() {
  var savedNames = getCapturedNames_(PROP_KEY);
  if (!savedNames) {
    try {
      savedNames = captureHighlightedColumnNames().columnNames;
    } catch (e) {
      throw new Error('No column names captured yet. Run captureHighlightedColumnNames() once while stock_valuation has the desired columns highlighted. (Auto-capture also failed: ' + e.message + ')');
    }
  }

  // Auto-create the target and mirror tabs on first run so nothing errors
  // out with "Sheet not found". Use forgiving lookup so a slightly-renamed
  // existing tab doesn't get duplicated.
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try { resolveSheet_(ss, TARGET_SHEET_NAME); }
  catch (_) { ss.insertSheet(TARGET_SHEET_NAME); }

  var result = syncBySavedNames_(SOURCE_SHEET_NAME, TARGET_SHEET_NAME, savedNames);
  var appendResult = appendToCombined_(ss, result.outRows);

  return {
    columnsCopied: result.columnsCopied,
    rowsCopied: result.rowsCopied,
    missingSavedColumns: result.missingSavedColumns,
    appendedToCombined: appendResult
  };
}

/**
 * DIAGNOSTIC — run this from the Apps Script editor when the DPR sync isn't
 * producing anything in stock_valuation_columns. It returns (and logs to the
 * Execution log) exactly what the sync sees: the captured column names, the
 * current stock_valuation header row, and which captured names match vs
 * don't. Nine times out of ten the mismatch (or missing capture) is right
 * there.
 */
function diagnoseDPR() {
  var ss  = SpreadsheetApp.getActiveSpreadsheet();
  var report = {
    sourceSheet: SOURCE_SHEET_NAME,
    spreadsheetName: ss.getName(),
    availableTabs: ss.getSheets().map(function (s) { return s.getName(); })
  };
  var src;
  try {
    src = resolveSheet_(ss, SOURCE_SHEET_NAME);
    report.sourceResolvedAs = src.getName();
  } catch (e) {
    report.error = e.message;
    Logger.log(JSON.stringify(report, null, 2));
    return report;
  }

  var lastCol = src.getLastColumn();
  var lastRow = src.getLastRow();
  report.rowCount     = lastRow;
  report.columnCount  = lastCol;
  report.currentHeaders = (lastCol > 0)
    ? src.getRange(1, 1, 1, lastCol).getValues()[0].map(normalizeHeader_)
    : [];

  report.savedColumnNames = getCapturedNames_(PROP_KEY);

  if (!report.savedColumnNames) {
    report.diagnosis = 'PROPERTY EMPTY: No captured column names in HIGHLIGHTED_COLUMN_NAMES. Highlight the desired columns in stock_valuation and run captureHighlightedColumnNames() once.';
  } else {
    var matched = [];
    var missing = [];
    var headerSet = {};
    report.currentHeaders.forEach(function (h) { if (h) headerSet[h] = true; });
    report.savedColumnNames.forEach(function (name) {
      if (headerSet[name]) matched.push(name);
      else missing.push(name);
    });
    report.matchedCount = matched.length;
    report.missingCount = missing.length;
    report.matched      = matched;
    report.missing      = missing;
    if (matched.length === 0) {
      report.diagnosis = 'ALL CAPTURED NAMES ARE MISSING: none of the saved names appear in the current stock_valuation header row. Either the header row changed spelling, or the wrong columns were captured. Re-run captureHighlightedColumnNames() with the desired columns highlighted.';
    } else if (missing.length > 0) {
      report.diagnosis = 'PARTIAL MATCH: ' + matched.length + ' names found in the current header, ' + missing.length + ' missing. Sync will still work — missing names are just skipped.';
    } else {
      report.diagnosis = 'OK: all ' + matched.length + ' captured names found in the current header. If stock_valuation_columns is still empty after uploads, the issue is in n8n (probably the HTTP node still needs Execute Once turned on).';
    }
  }

  Logger.log(JSON.stringify(report, null, 2));
  return report;
}

/**
 * Appends the freshly-written stock_valuation_columns rows to the bottom
 * of the `combined` tab. Never clears combined. Creates it if missing.
 * The header row is seeded only once, when `combined` is empty.
 */
function appendToCombined_(ss, freshRows) {
  var mirror;
  try { mirror = resolveSheet_(ss, MIRROR_SHEET_NAME); }
  catch (_) { mirror = ss.insertSheet(MIRROR_SHEET_NAME); }

  if (!freshRows || freshRows.length === 0) {
    return { rowsAppended: 0, columnsCopied: 0 };
  }

  var header   = freshRows[0];
  var dataRows = freshRows.slice(1);
  var numCols  = header.length;

  if (mirror.getLastRow() === 0) {
    mirror.getRange(1, 1, 1, numCols).setValues([header]);
  }

  if (dataRows.length > 0) {
    var startRow = mirror.getLastRow() + 1;
    mirror.getRange(startRow, 1, dataRows.length, numCols).setValues(dataRows);
  }

  return {
    rowsAppended: dataRows.length,
    columnsCopied: numCols,
    totalRowsInCombined: mirror.getLastRow() - 1
  };
}

// ============================================================================
// PO flow: po -> po_highlighted_columns. Wipe-and-rewrite, no history log.
// ============================================================================

function captureHighlightedColumnNamesPO() {
  return captureHighlightedNames_(PO_SOURCE_SHEET_NAME, PO_PROP_KEY);
}

function clearCapturedColumnNamesPO() {
  clearCapturedNames_(PO_PROP_KEY);
}

function syncCapturedColumnsToPOHighlighted() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  try { resolveSheet_(ss, PO_TARGET_SHEET_NAME); }
  catch (_) { ss.insertSheet(PO_TARGET_SHEET_NAME); }

  var savedNames = getCapturedNames_(PO_PROP_KEY);
  if (!savedNames) {
    try {
      savedNames = captureHighlightedColumnNamesPO().columnNames;
    } catch (e) {
      throw new Error('No PO column names captured yet. Run captureHighlightedColumnNamesPO() once while the po tab has the desired columns highlighted. (Auto-capture also failed: ' + e.message + ')');
    }
  }

  var result = syncBySavedNames_(PO_SOURCE_SHEET_NAME, PO_TARGET_SHEET_NAME, savedNames);
  return {
    columnsCopied: result.columnsCopied,
    rowsCopied: result.rowsCopied,
    missingSavedColumns: result.missingSavedColumns
  };
}
