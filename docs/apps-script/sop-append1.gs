var SHEET_ID = '1cORrogedEjG1ej5pursnTsdAGtsUwvxL7a06zosqYe8';

var CLR = {
  item:'#37474F',forecastH:'#1565C0',supplyH:'#2E7D32',
  typeH:'#455A64',dispatchH:'#00838F',closingH:'#E65100',
  shortH:'#C62828',surplusH:'#F9A825',insightH:'#6A1B9A',
  financeH:'#283593',
  itemL:'#ECEFF1',forecastL:'#E3F2FD',supplyL:'#E8F5E9',
  typeL:'#ECEFF1',dispatchL:'#E0F7FA',closingL:'#FFF3E0',
  shortL:'#FFEBEE',surplusL:'#FFFDE7',insightL:'#F3E5F5',
  financeL:'#E8EAF6',
};

var COL_GROUPS = [
  [1,3,CLR.item,CLR.itemL,'ITEM INFO'],
  [4,9,CLR.forecastH,CLR.forecastL,'FORECAST & DEMAND'],
  [10,14,CLR.supplyH,CLR.supplyL,'INVENTORY & SUPPLY'],
  [15,15,CLR.typeH,CLR.typeL,'TYPE'],
  [16,17,CLR.dispatchH,CLR.dispatchL,'DISPATCH'],
  [18,20,CLR.closingH,CLR.closingL,'CLOSING & SAFETY'],
  [21,25,CLR.shortH,CLR.shortL,'SHORTFALL & GAPS'],
  [26,28,CLR.surplusH,CLR.surplusL,'SURPLUS & EXCESS'],
  [29,33,CLR.insightH,CLR.insightL,'INSIGHTS & NARRATIVES'],
  [34,42,CLR.financeH,CLR.financeL,'FINANCIAL IMPACT'],
];

function num(v){if(v===null||v===undefined||v===''||v==='-')return 0;var n=typeof v==='number'?v:parseFloat(String(v).replace(/,/g,'').replace(/[^0-9.\-]/g,'').trim());return isNaN(n)?0:n;}
function pct(n,d){if(!d)return '';return Math.round(n/d*100)+'%';}
function fmt(v){if(v===0||v===null||v===undefined)return '';return Math.round(v*100)/100;}

function readSheet(ss,name){var sh=ss.getSheetByName(name);if(!sh||sh.getLastRow()<2)return [];return sh.getDataRange().getValues();}

/**
 * Build {values, groups} map: sum valCol keyed on keyCol.
 * grpCol is explicit so different tab layouts work.
 */
function buildSumMap(data,keyCol,valCol,grpCol){
  var map={},grpMap={};
  for(var i=1;i<data.length;i++){
    var key=String(data[i][keyCol]||'').trim();
    if(!key)continue;
    map[key]=(map[key]||0)+num(data[i][valCol]);
    if(grpCol!==undefined&&grpCol!==null&&!grpMap[key]&&data[i][grpCol])
      grpMap[key]=String(data[i][grpCol]).trim();
  }
  return {values:map,groups:grpMap};
}

function computeAppend1(){
  var ss=SpreadsheetApp.openById(SHEET_ID);

  /* ── Read source tabs (n8n-uploaded raw ERP data) ── */
  var dprData      = readSheet(ss,'DPR');
  var forecastData = readSheet(ss,'Forecast');
  var openStockRaw = readSheet(ss,'Opening Stock');
  var glData       = readSheet(ss,'Green Level');
  var salesRegData = readSheet(ss,'Sales Register');

  /* Optional tabs (may not exist yet) */
  var demandData  = readSheet(ss,'Actual Demand');
  var tradingData = readSheet(ss,'Trading Items');
  var aspData     = readSheet(ss,'ASP');
  var focusData   = readSheet(ss,'Focus');

  /* ── Build lookup maps with correct column indices ── */

  // DPR: item_code@4, receipt_qty@19 (=production), item_group@11
  var dpr = buildSumMap(dprData,4,19,11);

  // Forecast: item_code@8, forecast_qty@11, item_group@37
  var forecast = buildSumMap(forecastData,8,11,37);

  // Actual Demand: detect format (simple 3-col vs raw ERP)
  var demand;
  if(demandData.length>1){
    var hdr1=String(demandData[0][1]||'').trim().toLowerCase();
    if(hdr1==='item code'||hdr1==='item_code'){
      // Simple 3-col: Group | Item Code | Qty
      demand=buildSumMap(demandData,1,2,0);
    }else if(hdr1==='voucher_number'||hdr1==='voucher_type'){
      // Raw ERP format (same as DPR): item_code@4, issue_qty@24, item_group@11
      demand=buildSumMap(demandData,4,24,11);
    }else{
      demand=buildSumMap(demandData,1,2,0);
    }
  }else{
    demand={values:{},groups:{}};
  }

  // Sales Register: item_code@60, item_sales_qty@79, item_group@65
  var salesReg = buildSumMap(salesRegData,60,79,65);

  // DPR landed rates (replaces old DPR Valuation tab): item_code@4, landed_rate@14
  var dprRate={};
  for(var i=1;i<dprData.length;i++){
    var ic=String(dprData[i][4]||'').trim();
    if(ic&&!dprRate[ic])dprRate[ic]=num(dprData[i][14]);
  }

  // Trading adjustments (if tab exists)
  var tradingAdded={},tradingDeducted={};
  for(var i=1;i<tradingData.length;i++){
    var ic=String(tradingData[i][2]||'').trim();
    if(!ic)continue;
    tradingAdded[ic]=(tradingAdded[ic]||0)+num(tradingData[i][3]);
    tradingDeducted[ic]=(tradingDeducted[ic]||0)+num(tradingData[i][4]);
  }

  // Green Level: erp_code@4, jolly_code@5, mto_mts@6, green_level@7, family@0
  var glLookup={};
  for(var i=1;i<glData.length;i++){
    var erpCode  =String(glData[i][4]||'').trim();
    var jollyCode=String(glData[i][5]||'').trim();
    var info={
      type:      String(glData[i][6]||'TBC').trim().toUpperCase(),
      greenLevel:num(glData[i][7]),
      family:    String(glData[i][0]||'').trim()
    };
    if(erpCode&&erpCode!=='0')  glLookup[erpCode]=info;
    if(jollyCode&&jollyCode!=='0')glLookup[jollyCode]=info;
  }

  // Opening Stock: item_code@6, item_category@12,
  //   closing_qty_base_uom@36 (NOT opening_qty@31 – closing is the
  //   actual stock on hand used by S&OP), opening_landed_rate@43,
  //   item_group@10, site_code@0, location_code@5
  var openingQty={},openingRate={},openingGroup={},openingSeen={};
  for(var i=1;i<openStockRaw.length;i++){
    var ic  =String(openStockRaw[i][6]||'').trim();
    var cat =String(openStockRaw[i][12]||'').trim();
    if(!ic)continue;
    // Only count finished goods (all FG categories)
    if(cat.indexOf('FG')!==0)continue;
    // Deduplicate: same site + location + item = duplicate n8n row
    var site=String(openStockRaw[i][0]||'').trim();
    var loc =String(openStockRaw[i][5]||'').trim();
    var dedupKey=site+'|'+loc+'|'+ic;
    if(openingSeen[dedupKey])continue;
    openingSeen[dedupKey]=true;
    // Use closing_qty_base_uom (col 36) — represents actual stock on hand
    openingQty[ic]=(openingQty[ic]||0)+num(openStockRaw[i][36]);
    if(!openingRate[ic]) openingRate[ic]=num(openStockRaw[i][43]);
    if(!openingGroup[ic])openingGroup[ic]=String(openStockRaw[i][10]||'').trim();
  }

  // ASP (if tab exists)
  var aspMap={};
  for(var i=1;i<aspData.length;i++){
    var grp=String(aspData[i][1]||'').trim();
    if(grp&&grp!=='Total'&&grp!=='Particulars')aspMap[grp]=num(aspData[i][2]);
  }

  // Focus items (if tab exists)
  var focusSet={};
  for(var i=1;i<focusData.length;i++){
    var name=String(focusData[i][0]||'').trim();
    if(name)focusSet[name]=true;
  }

  /* ── Collect all unique item codes ── */
  var allCodes={};
  function addCodes(map){for(var k in map)allCodes[k]=true;}
  addCodes(dpr.values);addCodes(forecast.values);addCodes(demand.values);
  addCodes(salesReg.values);addCodes(openingQty);
  var itemCodes=Object.keys(allCodes).sort();
  Logger.log('Append1: computing '+itemCodes.length+' items');

  /* ── Compute each row ── */
  var rows=[];
  for(var idx=0;idx<itemCodes.length;idx++){
    var ic=itemCodes[idx];
    var gl=glLookup[ic]||{type:'TBC',greenLevel:0,family:''};
    var itemGroup=forecast.groups[ic]||dpr.groups[ic]||salesReg.groups[ic]||openingGroup[ic]||gl.family||'';
    var productClass=focusSet[itemGroup]?'Focus':'Regular';

    var D=forecast.values[ic]||0;
    var E=D;
    var F_adj=E-D;
    var G=demand.values[ic]||E;
    var H=G-D;
    var H_dir=D-G;

    var I_var,I_pct;
    if(D===0&&G===0){I_var=0;I_pct='';}
    else if(D===0){I_var=1;I_pct=G>0?0:1;}
    else{I_var=Math.abs(G-D)/D;I_pct=Math.max(0,Math.round((1-I_var)*10000)/10000);}

    var J=openingQty[ic]||0;
    var K=dpr.values[ic]||0;
    var L=tradingAdded[ic]||0;
    var M_ded=tradingDeducted[ic]||0;
    var N=J+K+L-M_ded;
    var O_type=gl.type;

    var P=salesReg.values[ic]||0;
    var Q_pct=G>0?Math.round(P/G*10000)/10000:'';
    var R=N-P;
    var S_gl=gl.greenLevel;
    var T=Math.max(R-S_gl,0);

    var U=Math.max(G-P,0);
    var V_gap=(P<G&&R>0)?Math.min(R,G-P):0;
    var Y_pds=Math.min(Math.max(D-P-R,0),Math.max(D-P,0));
    var W_sad=Math.max(U-V_gap-Y_pds,0);
    var X_dra=Math.max(V_gap+W_sad+Y_pds-U,0);

    var buildNeeded=Math.max(D+S_gl-J,0);
    var Z_surplus=Math.max(K-buildNeeded,0);
    var AA_exOp=Math.max(J-G-S_gl,0);
    var AB_exDisp=Math.max(P-G,0);
    var prodShortfall=Math.max(G-N,0);

    var salesTag =salesInsightTag(G,P,I_var);
    var salesNarr=salesNarrative(G,P,O_type,I_var,H_dir,AB_exDisp,U);
    var opsTag   =opsInsightTag(G,O_type,P,R,S_gl,prodShortfall,Z_surplus,F_adj,D);
    var opsNarr  =opsNarrative(G,K,O_type,R,S_gl,prodShortfall,Z_surplus);
    var opsCap   =opsCapacityNarrative(D,E,F_adj);

    var asp=aspMap[itemGroup]||0;
    var landedRate=openingRate[ic]||dprRate[ic]||0;

    rows.push([
      itemGroup,ic,productClass,
      fmt(D)||'',fmt(E)||'',fmt(F_adj)||'',fmt(G)||'',fmt(H)||'',I_pct,
      fmt(J)||'',fmt(K)||'',fmt(L)||'',fmt(M_ded)||'',fmt(N)||'',O_type,
      fmt(P)||'',Q_pct,fmt(R),fmt(S_gl)||'',fmt(T)||'',
      fmt(U)||'',fmt(V_gap)||'',fmt(W_sad)||'',fmt(X_dra)||'',fmt(Y_pds)||'',
      fmt(Z_surplus)||'',fmt(AA_exOp)||'',fmt(AB_exDisp)||'',
      salesTag,salesNarr,opsTag,opsNarr,opsCap,
      fmt(Z_surplus*landedRate)||'',fmt(AA_exOp*landedRate)||'',
      fmt(Math.max(E+S_gl-J,0))||'',
      fmt(Math.max(E+S_gl-J,0)>0?Math.min(K,Math.max(E+S_gl-J,0)):0)||'',
      fmt(Y_pds*asp)||'',fmt(V_gap*asp)||'',fmt(W_sad*asp)||'',
      fmt(X_dra*asp)||'',fmt(AB_exDisp*asp)||''
    ]);
  }

  /* ── Build group-label row and header row ── */
  var groupRow=[];
  var headers=[
    'Item Group','Item Code','Product Class',
    'Original Forecast','Committed Forecast','Ops Adjustment','Actual Sales Demand',
    'Additional Demand','Forecast Accuracy %',
    'Opening Inventory','Actual Production','Stock Adj (Added)','Stock Adj (Deducted)',
    'Total Available','Type (MTS/MTO)',
    'Actual Dispatch','Dispatch %','Closing Inventory','Green Level','Free Inventory',
    'Uncovered Shortfall','Dispatch Gap','Shortfall Add. Demand','Demand Reduction Adj',
    'Prod-Driven Shortfall','Production Surplus','Excess Opening Stock','Excess Dispatched',
    'Sales Insight Tag','Sales Narrative','Ops Insight Tag','Ops Narrative','Ops Capacity Narrative',
    'Surplus Prod (Rs)','Excess Op. Stock (Rs)','Build Required','Prod Counted',
    'Prod Shortfall (Rs)','Dispatch Gap (Rs)','Shortfall Add. Demand (Rs)',
    'Demand Reduction (Rs)','Excess Dispatch (Rs)'
  ];

  for(var g=0;g<COL_GROUPS.length;g++){
    var grp=COL_GROUPS[g];
    for(var c=grp[0];c<=grp[1];c++){groupRow[c-1]=(c===grp[0])?grp[4]:'';}
  }

  /* ── Delete + recreate Append1 (avoids Excel-conversion column groups) ── */
  var oldSheet=ss.getSheetByName('Append1');
  if(oldSheet){ss.deleteSheet(oldSheet);SpreadsheetApp.flush();}
  var sheet=ss.insertSheet('Append1');

  var allValues=[groupRow,headers].concat(rows);
  var neededRows=allValues.length;
  var neededCols=headers.length;
  var currentRows=sheet.getMaxRows();
  var currentCols=sheet.getMaxColumns();
  if(neededRows>currentRows)sheet.insertRowsAfter(currentRows,neededRows-currentRows);
  if(neededCols>currentCols)sheet.insertColumnsAfter(currentCols,neededCols-currentCols);

  /* ── Write data via Sheets API v4 in chunks ── */
  var WRITE_CHUNK=500;
  for(var c=0;c<allValues.length;c+=WRITE_CHUNK){
    var slice=allValues.slice(c,c+WRITE_CHUNK);
    var startRow=c+1;
    var range='Append1!A'+startRow;
    for(var attempt=1;attempt<=3;attempt++){
      try{
        Sheets.Spreadsheets.Values.update({values:slice},SHEET_ID,range,{valueInputOption:'RAW'});
        Logger.log('Chunk '+Math.floor(c/WRITE_CHUNK+1)+': wrote '+slice.length+' rows');
        break;
      }catch(e){
        Logger.log('Write attempt '+attempt+': '+e.message);
        if(attempt===3)throw e;
        Utilities.sleep(2000*attempt);
      }
    }
  }

  // Trim extra rows/cols
  var totalRows=sheet.getMaxRows();
  if(totalRows>neededRows)sheet.deleteRows(neededRows+1,totalRows-neededRows);
  var totalCols=sheet.getMaxColumns();
  if(totalCols>neededCols)sheet.deleteColumns(neededCols+1,totalCols-neededCols);

  /* ── FORMAT ── */
  formatSheet(sheet,headers.length,rows.length);

  logToClaudeLog(ss,'Append1 computed: '+rows.length+' items, '+headers.length+' columns');
  Logger.log('Done: '+rows.length+' items, '+headers.length+' columns.');
}

function formatSheet(sheet,numCols,numDataRows){
  var dataStart=3;
  var lastRow=dataStart+numDataRows-1;

  // Row 1: Group labels
  sheet.setRowHeight(1,32);
  for(var g=0;g<COL_GROUPS.length;g++){
    var grp=COL_GROUPS[g];
    var startC=grp[0],endC=grp[1],color=grp[2];
    var span=endC-startC+1;
    sheet.getRange(1,startC,1,span)
      .setBackground(color).setFontColor('#FFFFFF').setFontWeight('bold')
      .setFontSize(10).setVerticalAlignment('middle').setHorizontalAlignment('center');
  }

  // Row 2: Column headers
  sheet.setRowHeight(2,42);
  for(var g=0;g<COL_GROUPS.length;g++){
    var grp=COL_GROUPS[g];
    var startC=grp[0],endC=grp[1],color=grp[2];
    var span=endC-startC+1;
    sheet.getRange(2,startC,1,span)
      .setBackground(color).setFontColor('#FFFFFF').setFontWeight('bold')
      .setFontSize(9).setWrap(true).setVerticalAlignment('middle').setHorizontalAlignment('center');
  }

  // Bottom border under headers
  sheet.getRange(2,1,1,numCols).setBorder(null,null,true,null,null,null,
    '#37474F',SpreadsheetApp.BorderStyle.SOLID_MEDIUM);

  // Data rows
  if(numDataRows>0){
    for(var g=0;g<COL_GROUPS.length;g++){
      var grp=COL_GROUPS[g];
      var startC=grp[0],endC=grp[1],tint=grp[3];
      var span=endC-startC+1;
      sheet.getRange(dataStart,startC,numDataRows,span)
        .setFontSize(9).setVerticalAlignment('middle');
      for(var row=dataStart;row<=lastRow;row++){
        sheet.getRange(row,startC,1,span)
          .setBackground((row%2===0)?tint:'#FFFFFF');
      }
    }

    // Alignment
    sheet.getRange(dataStart,1,numDataRows,3).setHorizontalAlignment('left');
    sheet.getRange(dataStart,15,numDataRows,1).setHorizontalAlignment('center');
    sheet.getRange(dataStart,29,numDataRows,5).setHorizontalAlignment('left').setWrap(true);
    sheet.getRange(dataStart,4,numDataRows,6).setHorizontalAlignment('right');
    sheet.getRange(dataStart,10,numDataRows,5).setHorizontalAlignment('right');
    sheet.getRange(dataStart,16,numDataRows,5).setHorizontalAlignment('right');
    sheet.getRange(dataStart,21,numDataRows,8).setHorizontalAlignment('right');
    sheet.getRange(dataStart,34,numDataRows,9).setHorizontalAlignment('right');

    // Number formats
    var numFmt='#,##0';
    var rsFmt='#,##0.00';
    var pctFmt='0.00%';
    sheet.getRange(dataStart,4,numDataRows,5).setNumberFormat(numFmt);   // Forecast cols D-H
    sheet.getRange(dataStart,9,numDataRows,1).setNumberFormat(pctFmt);   // Forecast Accuracy (ratio→%)
    sheet.getRange(dataStart,10,numDataRows,5).setNumberFormat(numFmt);  // Supply cols J-N
    sheet.getRange(dataStart,16,numDataRows,1).setNumberFormat(numFmt);  // Dispatch qty
    sheet.getRange(dataStart,17,numDataRows,1).setNumberFormat(pctFmt);  // Dispatch % (ratio→%)
    sheet.getRange(dataStart,18,numDataRows,3).setNumberFormat(numFmt);  // Closing, GL, Free
    sheet.getRange(dataStart,21,numDataRows,8).setNumberFormat(numFmt);  // Shortfall & Surplus
    sheet.getRange(dataStart,34,numDataRows,2).setNumberFormat(rsFmt);   // Financial Rs
    sheet.getRange(dataStart,36,numDataRows,2).setNumberFormat(numFmt);  // Build req, prod counted
    sheet.getRange(dataStart,38,numDataRows,5).setNumberFormat(rsFmt);   // More financial

    // Conditional formatting
    var rule1=SpreadsheetApp.newConditionalFormatRule()
      .whenNumberGreaterThan(0).setFontColor('#C62828')
      .setRanges([sheet.getRange(dataStart,21,numDataRows,5)]).build();
    var rule2=SpreadsheetApp.newConditionalFormatRule()
      .whenNumberGreaterThan(0).setFontColor('#2E7D32')
      .setRanges([sheet.getRange(dataStart,26,numDataRows,3)]).build();
    var rule3=SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo('Focus').setFontColor('#1565C0').setBold(true)
      .setRanges([sheet.getRange(dataStart,3,numDataRows,1)]).build();
    sheet.setConditionalFormatRules([rule1,rule2,rule3]);
  }

  // Freeze rows and columns
  sheet.setFrozenRows(2);
  sheet.setFrozenColumns(2);

  Logger.log('Formatting applied.');
}

/**
 * Format existing Append1 data without recomputing.
 * Useful when data is already written but needs re-formatting.
 */
function formatExistingAppend1(){
  var ss=SpreadsheetApp.openById(SHEET_ID);
  var sheet=ss.getSheetByName('Append1');
  if(!sheet){Logger.log('No Append1 sheet found');return;}
  var lastRow=sheet.getLastRow();
  var lastCol=sheet.getLastColumn();
  if(lastRow<3||lastCol<42){Logger.log('Append1 has insufficient data');return;}

  // Check if row 1 is group labels or column headers
  var r1=sheet.getRange(1,1).getValue();
  var r2=sheet.getRange(2,1).getValue();
  var dataStart=3;
  if(r1==='Item Group'){
    // No group row — insert one
    sheet.insertRowBefore(1);
    var groupRow=[];
    for(var g=0;g<COL_GROUPS.length;g++){
      var grp=COL_GROUPS[g];
      for(var c=grp[0];c<=grp[1];c++){groupRow[c-1]=(c===grp[0])?grp[4]:'';}
    }
    sheet.getRange(1,1,1,groupRow.length).setValues([groupRow]);
    lastRow=sheet.getLastRow();
  }

  var numDataRows=lastRow-2;
  formatSheet(sheet,Math.min(lastCol,42),numDataRows);
  Logger.log('formatExistingAppend1 done: '+numDataRows+' data rows formatted.');
}

function salesInsightTag(G,P,I_var){
  var tags=[];
  if(G>0&&P>G*1.1)tags.push('Over-Delivered');
  else if(G>0&&P>=G*0.9&&P<=G*1.1)tags.push('On Target');
  else if(G>0&&P<G*0.9)tags.push('Short Delivery');
  if(I_var===0)tags.push('Forecast Bullseye');
  else if(I_var<=0.1)tags.push('Forecast Drift (Minor)');
  else if(I_var<=0.3)tags.push('Forecast Drift (Moderate)');
  else if(I_var>0.3)tags.push('Forecast Drift (Major)');
  return tags.join(' | ');
}

function salesNarrative(G,P,M,I_var,H_dir,AB_excess,U_short){
  var parts=[];
  if(G>0)parts.push('Dispatch '+Math.round(P/G*100)+'% of committed ('+commaFmt(P)+' vs '+commaFmt(G)+').');
  else parts.push('Dispatch '+commaFmt(P)+' units (no committed demand).');
  if(M==='MTS')parts.push('MTS item.');
  else if(M==='MTO')parts.push('MTO item.');
  if(I_var===0)parts.push('Forecast hit dead-on.');
  else if(I_var<=0.1&&H_dir>0)parts.push('Forecast tightening '+Math.round(I_var*100)+'% - minor cut.');
  else if(I_var<=0.1&&H_dir<0)parts.push('Forecast raised '+Math.round(I_var*100)+'% - minor uplift.');
  else if(I_var<=0.3&&H_dir>0)parts.push('Forecast cut '+Math.round(I_var*100)+'% - demand softened.');
  else if(I_var<=0.3&&H_dir<0)parts.push('Forecast raised '+Math.round(I_var*100)+'% - late orders pulled in.');
  else if(I_var>0.3&&H_dir>0)parts.push('Major forecast cut '+Math.round(I_var*100)+'% - severe over-promise.');
  else if(I_var>0.3&&H_dir<0)parts.push('Major forecast uplift '+Math.round(I_var*100)+'% - late demand surge.');
  if(AB_excess>0)parts.push('Action: review over-commit of '+commaFmt(AB_excess)+' units.');
  else if(U_short>0)parts.push('Action: recover shortfall of '+commaFmt(U_short)+' units.');
  else parts.push('No open commitment gap.');
  return parts.join(' ');
}

function opsInsightTag(G,M,P,R,S_gl,prodShortfall,Z_surplus,F_adj,D){
  var tags=[];
  if(prodShortfall>0)tags.push('Production Shortfall');
  if(M==='MTS'){
    if(S_gl>0&&R<S_gl*0.5)tags.push('Stock-Out Risk');
    else if(S_gl>0&&R<S_gl)tags.push('Below Safety');
    if(G>0&&Z_surplus>G*0.5)tags.push('Excess Inventory');
    else if(Z_surplus>0)tags.push('Production Surplus');
  }
  if(M==='MTO'){
    if(Z_surplus>0)tags.push('Over-Production');
    else if(R>0&&P>=G)tags.push('Unsold MTO Stock');
  }
  if(D>0&&F_adj<0){
    var ratio=Math.abs(F_adj)/D;
    if(ratio>0.3)tags.push('Capacity Gap (Major)');
    else if(ratio>0.1)tags.push('Capacity Gap (Moderate)');
    else tags.push('Capacity Gap (Minor)');
  }else if(F_adj>0)tags.push('Ops Over-Commit');
  if(tags.length===0)tags.push('Healthy Stock');
  return tags.join(' | ');
}

function opsNarrative(G,K,M,R,S_gl,prodShortfall,Z_surplus){
  var parts=[];
  parts.push('Produced '+commaFmt(K)+' units against committed '+commaFmt(G)+' units.');
  if(prodShortfall>0)parts.push('Shortfall of '+commaFmt(prodShortfall)+' units.');
  if(M==='MTS'&&S_gl>0&&R<S_gl){
    var cover=S_gl>0?Math.round(R/S_gl*10)/10:0;
    parts.push('Closing '+commaFmt(R)+' units. Green level '+commaFmt(S_gl)+' ('+cover+'x cover) - Safety breach.');
  }
  if(M==='MTS'&&G>0&&Z_surplus>G*0.5)parts.push('Excess build-up of '+commaFmt(Z_surplus)+' units.');
  if(M==='MTO'&&Z_surplus>0)parts.push('Red flag: produced '+commaFmt(Z_surplus)+' units more than ordered.');
  if(prodShortfall===0&&Z_surplus===0){
    if((M==='MTS'&&R>=S_gl)||(M==='MTO'&&R===0))parts.push('Production and inventory healthy.');
  }
  return parts.join(' ');
}

function opsCapacityNarrative(D,E,F){
  if(F===0)return 'Ops accepted Sales forecast in full. No capacity gap at plan stage.';
  var pctStr=D>0?Math.round(Math.abs(F)/D*100)+'%':'n/a';
  if(F<0){
    if(D>0&&Math.abs(F)/D>0.3)return 'Ops cut '+commaFmt(Math.abs(F))+' units (-'+pctStr+'). Major capacity gap.';
    if(D>0&&Math.abs(F)/D>0.1)return 'Ops cut '+commaFmt(Math.abs(F))+' units (-'+pctStr+'). Moderate gap.';
    return 'Ops cut '+commaFmt(Math.abs(F))+' units (-'+pctStr+'). Minor adjustment.';
  }
  return 'Ops over-committed by '+commaFmt(F)+' units (+'+pctStr+').';
}

function commaFmt(n){
  if(n===0||n===null||n===undefined)return '0';
  return Math.round(n).toLocaleString('en-IN');
}

function logToClaudeLog(ss,message){
  var logSheet=ss.getSheetByName('Claude Log');
  if(!logSheet)return;
  logSheet.appendRow([new Date(),'Apps Script','computeAppend1',message]);
}

function doPost(e){
  try{computeAppend1();return ContentService.createTextOutput(JSON.stringify({ok:true,message:'Append1 recomputed'})).setMimeType(ContentService.MimeType.JSON);}
  catch(err){return ContentService.createTextOutput(JSON.stringify({ok:false,error:err.message})).setMimeType(ContentService.MimeType.JSON);}
}

function doGet(e){
  try{computeAppend1();return ContentService.createTextOutput(JSON.stringify({ok:true,message:'Append1 recomputed via GET'})).setMimeType(ContentService.MimeType.JSON);}
  catch(err){return ContentService.createTextOutput(JSON.stringify({ok:false,error:err.message})).setMimeType(ContentService.MimeType.JSON);}
}
