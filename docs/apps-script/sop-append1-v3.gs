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
function fmt(v){if(v===0||v===null||v===undefined)return '';return Math.round(v*100)/100;}

function readSheet(ss,name){var sh=ss.getSheetByName(name);if(!sh||sh.getLastRow()<2)return [];return sh.getDataRange().getValues();}

/**
 * Build {values:{code:sum}, groups:{code:group}} from simple summary tab.
 * keyCol = item code column, valCol = value column, grpCol = group column.
 */
function buildMap(data,keyCol,valCol,grpCol){
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

/* ================================================================
   computeAppend1 -- V3: reads from pre-aggregated summary tabs
   ================================================================ */
function computeAppend1(){
  var ss=SpreadsheetApp.openById(SHEET_ID);

  /* ---- Read PRE-AGGREGATED summary tabs ---- */
  // Original Forecast: col0=Group, col1=Code, col2=Forecast
  var origFcData = readSheet(ss,'Original Forecast');
  // Actual Demand: col0=Group, col1=Code, col2=Demand
  var actDemData = readSheet(ss,'Actual Demand');
  // DPR Valuation: col0=Group, col1=Code, col2=TotalDPR, col3=Value, col4=Rate
  var dprValData = readSheet(ss,'DPR Valuation');
  // Stock Ledger Report: col0=Group, col1=Code, col2=TotalDPR (production)
  var slrData    = readSheet(ss,'Stock Ledger Report');
  // Sales Invoice Register Report: col0=Group, col1=Code, col2=TotalSalesQty
  var sirrData   = readSheet(ss,'Sales Invoice Register Report');
  // Trading Items: col0=Voucher, col1=Group, col2=Code, col3=Receipt, col4=Issue
  var tradData   = readSheet(ss,'Stock Ledger Report- Trading It');

  /* ---- Read LOOKUP tabs ---- */
  // GL & Type: col1=Family, col5=ERPCode, col6=JollyCode, col7=MTO/MTS, col8=GL
  var glData     = readSheet(ss,'GL & Type');
  // ASP: col1=GroupDesc, col2=FinanceASP
  var aspData    = readSheet(ss,'ASP');

  /* ---- Read RAW tab (still needs aggregation) ---- */
  var openStockRaw = readSheet(ss,'Opening Stock');

  /* ---- Fallback: existing n8n tabs ---- */
  var forecastData = readSheet(ss,'Forecast');
  var dprRawData   = readSheet(ss,'DPR');
  var salesRegData = readSheet(ss,'Sales Register');

  /* ================================================================
     BUILD LOOKUP MAPS
     ================================================================ */

  // -- Original Forecast (summary): Group@0, Code@1, Qty@2
  var origForecast = buildMap(origFcData, 1, 2, 0);

  // -- Actual Demand (summary): Group@0, Code@1, Qty@2
  var actDemand = buildMap(actDemData, 1, 2, 0);

  // -- Production from DPR Valuation (summary): Group@0, Code@1, Qty@2
  var production = buildMap(dprValData, 1, 2, 0);

  // -- Production value and rate from DPR Valuation
  var prodValue={}, prodRate={};
  for(var i=1;i<dprValData.length;i++){
    var ic=String(dprValData[i][1]||'').trim();
    if(!ic)continue;
    prodValue[ic]=(prodValue[ic]||0)+num(dprValData[i][3]);
    if(!prodRate[ic])prodRate[ic]=num(dprValData[i][4]);
  }

  // -- Fallback production from Stock Ledger Report
  var slrProd = buildMap(slrData, 1, 2, 0);

  // -- Dispatch from Sales Invoice Register Report (summary): Group@0, Code@1, Qty@2
  var dispatch = buildMap(sirrData, 1, 2, 0);

  // -- Trading Items: aggregate Receipt (col3) and Issue (col4) per Code (col2)
  var tradingAdded={}, tradingDeducted={}, tradingGroups={};
  for(var i=1;i<tradData.length;i++){
    var ic=String(tradData[i][2]||'').trim();
    if(!ic)continue;
    tradingAdded[ic]=(tradingAdded[ic]||0)+num(tradData[i][3]);
    tradingDeducted[ic]=(tradingDeducted[ic]||0)+num(tradData[i][4]);
    if(!tradingGroups[ic])tradingGroups[ic]=String(tradData[i][1]||'').trim();
  }

  // -- GL & Type lookup: keyed on ERP Code and Jolly Code
  var glLookup={};
  for(var i=1;i<glData.length;i++){
    var erpCode  =String(glData[i][5]||'').trim();
    var jollyCode=String(glData[i][6]||'').trim();
    var info={
      type:      String(glData[i][7]||'TBC').trim().toUpperCase(),
      greenLevel:num(glData[i][8]),
      family:    String(glData[i][1]||'').trim()
    };
    if(erpCode&&erpCode!=='0')  glLookup[erpCode]=info;
    if(jollyCode&&jollyCode!=='0')glLookup[jollyCode]=info;
  }

  // -- ASP lookup: keyed on Item Group Description
  var aspMap={};
  for(var i=1;i<aspData.length;i++){
    var grp=String(aspData[i][1]||'').trim();
    if(grp&&grp!=='0')aspMap[grp]=num(aspData[i][2]);
  }

  // -- Opening Stock: aggregate closing_qty_base_uom@36 per item_code@6
  //    Filter: item_category@12 starts with 'FG'
  //    Dedup: site@0 + location@5 + item composite key
  var openingQty={},openingRate={},openingGroup={},openingSeen={};
  for(var i=1;i<openStockRaw.length;i++){
    var ic  =String(openStockRaw[i][6]||'').trim();
    var cat =String(openStockRaw[i][12]||'').trim();
    if(!ic)continue;
    if(cat.indexOf('FG')!==0)continue;
    var site=String(openStockRaw[i][0]||'').trim();
    var loc =String(openStockRaw[i][5]||'').trim();
    var dedupKey=site+'|'+loc+'|'+ic;
    if(openingSeen[dedupKey])continue;
    openingSeen[dedupKey]=true;
    openingQty[ic]=(openingQty[ic]||0)+num(openStockRaw[i][36]);
    if(!openingRate[ic]) openingRate[ic]=num(openStockRaw[i][43]);
    if(!openingGroup[ic])openingGroup[ic]=String(openStockRaw[i][10]||'').trim();
  }

  // -- Fallback: Forecast from n8n raw tab (item_code@8, forecast_qty@11, group@37)
  var fallbackForecast = buildMap(forecastData, 8, 11, 37);

  // -- Fallback: DPR raw production (item_code@4, receipt_qty@19, group@11)
  var fallbackDPR = buildMap(dprRawData, 4, 19, 11);

  // -- Fallback: DPR raw rate (item_code@4, landed_rate@14)
  var fallbackRate={};
  for(var i=1;i<dprRawData.length;i++){
    var ic=String(dprRawData[i][4]||'').trim();
    if(ic&&!fallbackRate[ic])fallbackRate[ic]=num(dprRawData[i][14]);
  }

  // -- Fallback: Sales Register dispatch (item_code@60, sales_qty@79, group@65)
  var fallbackDispatch = buildMap(salesRegData, 60, 79, 65);

  /* ================================================================
     BUILD MASTER ITEM LIST
     ================================================================ */
  var allItems={};
  var sources=[origForecast,actDemand,production,slrProd,dispatch,fallbackForecast,fallbackDPR,fallbackDispatch];
  for(var s=0;s<sources.length;s++){
    for(var k in sources[s].values) allItems[k]=true;
  }
  for(var k in openingQty) allItems[k]=true;

  // Get group for each item (priority: origForecast > actDemand > production > GL > opening > fallback)
  function getGroup(ic){
    return origForecast.groups[ic]||actDemand.groups[ic]||production.groups[ic]
      ||dispatch.groups[ic]||tradingGroups[ic]||openingGroup[ic]
      ||fallbackForecast.groups[ic]||fallbackDPR.groups[ic]||fallbackDispatch.groups[ic]||'';
  }

  // Helper: get value with fallback
  function getVal(primary, fallback, ic){
    if(primary.values[ic]!==undefined&&primary.values[ic]!==0) return primary.values[ic];
    if(fallback&&fallback.values[ic]!==undefined) return fallback.values[ic];
    return 0;
  }

  /* ================================================================
     COMPUTE ROWS
     ================================================================ */
  var items=Object.keys(allItems).sort();
  var rows=[];

  for(var idx=0;idx<items.length;idx++){
    var ic=items[idx];
    var grp=getGroup(ic);
    var gl=glLookup[ic]||{type:'TBC',greenLevel:0,family:''};
    var itemGroup=grp||gl.family||'Unknown';

    // Product Class: Regular unless in Focus tab (simplified)
    var productClass='Regular';

    // Col D: Original Forecast
    var D=getVal(origForecast, fallbackForecast, ic);
    // Col E: Committed Forecast (same as Original unless manually adjusted)
    var E=D;
    // Col F: Ops Adjustment = D - E
    var F=D-E; // 0 unless we add manual adjustment support
    // Col G: Actual Sales Demand
    var G=getVal(actDemand, {values:{}}, ic);
    // If no Actual Demand tab data, use forecast as demand (same as reference behavior)
    if(G===0&&D>0) G=D;
    // Col H: Additional Demand = max(0, G - E)
    var H=Math.max(0, G-E);
    if(G<=E) H=0;
    // Col I: Forecast Accuracy % = 1 - |G - D| / D (decimal ratio)
    var I_var=0, I_pct='';
    if(D>0){
      I_var=Math.abs(G-D)/D;
      I_pct=Math.max(0,Math.round((1-I_var)*10000)/10000);
    } else if(G===0){
      I_pct=1;I_var=0;
    } else {
      I_pct=0;I_var=1;
    }

    // Col J: Opening Inventory
    var J=openingQty[ic]||0;
    // Col K: Actual Production (summary > fallback)
    var K=production.values[ic]||slrProd.values[ic]||fallbackDPR.values[ic]||0;
    // Col L: Stock Adj Added (trading)
    var L=tradingAdded[ic]||0;
    // Col M_val: Stock Adj Deducted (trading)
    var M_val=tradingDeducted[ic]||0;
    // Col N_val: Total Available = J + K + L - M
    var N_val=J+K+L-M_val;
    // Col O: Type (MTS/MTO)
    var O_type=gl.type||'TBC';
    // Col P: Actual Dispatch (summary > fallback)
    var P=dispatch.values[ic]||fallbackDispatch.values[ic]||0;
    // Col Q: Dispatch % = P / E (decimal ratio)
    var Q=E>0?Math.round(P/E*10000)/10000:'';
    // Col R: Closing Inventory = N - P
    var R_val=N_val-P;
    // Col S: Green Level
    var S_val=gl.greenLevel||0;
    // Col T: Free Inventory = R - S
    var T_val=R_val-S_val;

    // SHORTFALL & GAPS (cols U-Y, sheet cols 21-25)
    // Col U: Uncovered Shortfall = max(0, E - N_val) -- demand exceeds total available
    var U=Math.max(0, E-N_val);
    // Col V: Dispatch Gap = max(0, min(E, N_val) - P) -- could ship but didn't
    var V=Math.max(0, Math.min(E, N_val)-P);
    // Col W: Shortfall on Additional Demand = H when additional demand can't be covered
    var W_val=(H>0&&N_val<G)?Math.min(H, Math.max(0,G-N_val)):0;
    // Col X: Demand Reduction Adjustment = max(0, D - E) -- sales pulled back
    var X_val=Math.max(0, D-E);
    // Col Y: Production-Driven Shortfall = max(0, E - J - K) -- need more than opening+production
    var Y_val=Math.max(0, E-J-K);

    // SURPLUS & EXCESS (cols Z-AB, sheet cols 26-28)
    // Col Z: Production Surplus = max(0, K - max(0, E - J))
    var Z_val=Math.max(0, K-Math.max(0, E-J));
    // Col AA: Excess Opening Stock = max(0, J - E - S_val)
    var AA=Math.max(0, J-E-S_val);
    // Col AB: Excess Dispatched = max(0, P - E) -- shipped more than committed
    var AB=Math.max(0, P-E);

    /* ---- INSIGHTS & NARRATIVES (cols AC-AG, sheet cols 29-33) ---- */
    // Sales Insight Tag (col AC/29)
    var salesTags=[];
    // Dispatch tags
    if(P>0&&E>0){
      if(P>E*1.1) salesTags.push('Over-Delivered');
      else if(P>=E*0.9&&P<=E*1.1) salesTags.push('On Target');
      else if(P<E*0.9) salesTags.push('Short Delivery');
    }
    // Forecast tags
    if(D>0){
      if(I_var===0) salesTags.push('Forecast Bullseye');
      else if(I_var<=0.1) salesTags.push('Forecast Drift (Minor)');
      else if(I_var<=0.3) salesTags.push('Forecast Drift (Moderate)');
      else salesTags.push('Forecast Drift (Major)');
    }
    var AC_tag=salesTags.join(' | ');

    // Sales Insight Narrative (col AD/30)
    var adParts=[];
    // Dispatch header (always)
    if(E>0){
      var dispPct=Math.round(P/E*100);
      adParts.push('Dispatch '+dispPct+'% of committed ('+Math.round(P).toLocaleString()+' vs '+Math.round(E).toLocaleString()+').');
    }
    // Type context
    if(O_type==='MTO') adParts.push('MTO item -- demand is order-driven.');
    else if(O_type==='MTS') adParts.push('MTS item -- stock-driven replenishment.');
    // Forecast context
    if(D>0){
      if(I_var===0) adParts.push('Forecast hit dead-on.');
      else if(I_var<=0.1){
        if(G<D) adParts.push('Minor demand shortfall vs forecast.');
        else adParts.push('Minor demand uplift vs forecast.');
      } else if(I_var<=0.3){
        if(G<D) adParts.push('Moderate demand cut vs forecast.');
        else adParts.push('Moderate demand uplift vs forecast.');
      } else {
        if(G<D) adParts.push('Major demand cut vs forecast ('+Math.round(I_var*100)+'% variance).');
        else adParts.push('Major demand uplift vs forecast ('+Math.round(I_var*100)+'% variance).');
      }
    }
    // Over-commit action
    if(AB>0) adParts.push('Action: review over-commit of '+Math.round(AB).toLocaleString()+' units.');
    // Under-delivery action
    if(V>0) adParts.push('Action: investigate dispatch gap of '+Math.round(V).toLocaleString()+' units.');
    var AD_narr=adParts.join(' ');

    // Ops Insight Tag (col AE/31)
    var opsTags=[];
    if(R_val>0&&O_type==='MTO'&&P>0) opsTags.push('Unsold MTO Stock');
    if(Z_val>0) opsTags.push('Over-Production');
    if(Y_val>0) opsTags.push('Production Shortfall');
    if(R_val<0) opsTags.push('Stock Deficit');
    if(AA>0) opsTags.push('Excess Stock');
    var AE_tag=opsTags.join(' | ');

    // Ops Insight Narrative (col AF/32)
    var afParts=[];
    if(R_val!==0) afParts.push('Closing '+Math.round(Math.abs(R_val)).toLocaleString()+' units'+(R_val<0?' (deficit)':'')+'. ');
    if(O_type==='MTO'&&R_val>0&&P>0){
      afParts.push('MTO -- stock should be near zero post-dispatch.');
      if(Z_val>0) afParts.push('Red flag -- produced more than ordered by '+Math.round(Z_val).toLocaleString()+' units.');
      afParts.push('Unsold MTO stock -- investigate.');
    }
    if(O_type==='MTS'){
      if(T_val<0) afParts.push('Below green level by '+Math.round(Math.abs(T_val)).toLocaleString()+' units -- replenish.');
      else if(AA>0) afParts.push('Excess stock of '+Math.round(AA).toLocaleString()+' above demand+safety.');
    }
    if(Y_val>0) afParts.push('Produced '+Math.round(K).toLocaleString()+' against committed '+Math.round(E).toLocaleString()+'. Shortfall of '+Math.round(Y_val).toLocaleString()+' units.');
    var AF_narr=afParts.join(' ');

    // S&OP Alignment (col AG/33)
    var AG_align='';
    if(D===E||F===0) AG_align='Ops accepted Sales forecast in full. No capacity gap at plan stage.';
    else if(E<D) AG_align='Ops reduced forecast by '+Math.round(D-E).toLocaleString()+' units. Capacity constraint flagged.';
    else AG_align='Ops increased commitment by '+Math.round(E-D).toLocaleString()+' above original forecast.';

    /* ---- FINANCIAL IMPACT (cols AH-AP, sheet cols 34-42) ---- */
    var rate=prodRate[ic]||openingRate[ic]||fallbackRate[ic]||0;
    var asp=aspMap[itemGroup]||0;
    var finRate=asp>0?asp:rate; // prefer ASP, fallback to production rate

    // Col AH (34): Opening Inventory Value = J * rate
    var AH=J>0?Math.round(J*rate*100)/100:0;
    // Col AI (35): Production Value = from DPR Valuation or K * rate
    var AI=prodValue[ic]||Math.round(K*rate*100)/100;
    // Col AJ (36): Stock Adj Added Value
    var AJ=L>0?Math.round(L*rate*100)/100:0;
    // Col AK (37): Stock Adj Deducted Value
    var AK=M_val>0?Math.round(M_val*rate*100)/100:0;
    // Col AL (38): Dispatch Value = P * finRate
    var AL=P>0?Math.round(P*finRate*100)/100:0;
    // Col AM (39): Closing Inventory Value = R * rate
    var AM=R_val>0?Math.round(R_val*rate*100)/100:0;
    // Col AN (40): Surplus Value = Z * rate
    var AN=Z_val>0?Math.round(Z_val*rate*100)/100:0;
    // Col AO (41): Shortfall Value = Y * rate
    var AO=Y_val>0?Math.round(Y_val*rate*100)/100:0;
    // Col AP (42): Excess Opening Value = AA * rate
    var AP=AA>0?Math.round(AA*rate*100)/100:0;

    // Build row (42 columns)
    rows.push([
      /* 1  A  */ itemGroup,
      /* 2  B  */ ic,
      /* 3  C  */ productClass,
      /* 4  D  */ D||'',
      /* 5  E  */ E||'',
      /* 6  F  */ F||'',
      /* 7  G  */ G||'',
      /* 8  H  */ H||'',
      /* 9  I  */ I_pct===''?'':I_pct,
      /* 10 J  */ J||'',
      /* 11 K  */ K||'',
      /* 12 L  */ L||'',
      /* 13 M  */ M_val||'',
      /* 14 N  */ N_val||'',
      /* 15 O  */ O_type,
      /* 16 P  */ P||'',
      /* 17 Q  */ Q,
      /* 18 R  */ R_val!==0?R_val:'',
      /* 19 S  */ S_val||'',
      /* 20 T  */ T_val!==0?T_val:'',
      /* 21 U  */ U||'',
      /* 22 V  */ V||'',
      /* 23 W  */ W_val||'',
      /* 24 X  */ X_val||'',
      /* 25 Y  */ Y_val||'',
      /* 26 Z  */ Z_val||'',
      /* 27 AA */ AA||'',
      /* 28 AB */ AB||'',
      /* 29 AC */ AC_tag,
      /* 30 AD */ AD_narr,
      /* 31 AE */ AE_tag,
      /* 32 AF */ AF_narr,
      /* 33 AG */ AG_align,
      /* 34 AH */ AH||'',
      /* 35 AI */ AI||'',
      /* 36 AJ */ AJ||'',
      /* 37 AK */ AK||'',
      /* 38 AL */ AL||'',
      /* 39 AM */ AM||'',
      /* 40 AN */ AN||'',
      /* 41 AO */ AO||'',
      /* 42 AP */ AP||''
    ]);
  }

  // Sort by Item Group then Item Code
  rows.sort(function(a,b){
    if(a[0]<b[0])return -1;if(a[0]>b[0])return 1;
    if(a[1]<b[1])return -1;if(a[1]>b[1])return 1;
    return 0;
  });

  /* ================================================================
     WRITE TO APPEND1 SHEET
     ================================================================ */
  var sheet=ss.getSheetByName('Append1');
  if(!sheet){sheet=ss.insertSheet('Append1');}
  sheet.clear();

  // Headers
  var hdr1=['ITEM INFO','','','FORECAST & DEMAND','','','','','',
            'INVENTORY & SUPPLY','','','','','TYPE',
            'DISPATCH','','CLOSING & SAFETY','','',
            'SHORTFALL & GAPS','','','','',
            'SURPLUS & EXCESS','','',
            'INSIGHTS & NARRATIVES','','','','',
            'FINANCIAL IMPACT','','','','','','','',''];
  var hdr2=['Item Group','Item Code','Product Class',
            'Original Forecast','Committed Forecast','Ops Adjustment',
            'Actual Sales Demand','Additional Demand','Forecast Accuracy %',
            'Opening Inventory','Actual Production','Stock Adj (Added)','Stock Adj (Deducted)','Total Available',
            'Type (MTS/MTO)',
            'Actual Dispatch','Dispatch %',
            'Closing Inventory','Green Level','Free Inventory',
            'Uncovered Shortfall','Dispatch Gap','Shortfall on Addl Demand','Demand Reduction Adj','Production-Driven Shortfall',
            'Production Surplus','Excess Opening Stock','Excess Dispatched',
            'Sales Insight Tag','Sales Narrative','Ops Insight Tag','Ops Narrative','S&OP Alignment',
            'Opening Value','Production Value','Trading Added Value','Trading Deducted Value',
            'Dispatch Value','Closing Value','Surplus Value','Shortfall Value','Excess Opening Value'];

  // Write headers
  sheet.getRange(1,1,1,42).setValues([hdr1]);
  sheet.getRange(2,1,1,42).setValues([hdr2]);

  // Write data
  if(rows.length>0){
    sheet.getRange(3,1,rows.length,42).setValues(rows);
  }

  // Format
  formatSheet(sheet,rows.length);

  Logger.log('Append1 V3: '+rows.length+' items, 42 columns');
  return rows.length;
}

/* ================================================================
   FORMAT SHEET
   ================================================================ */
function formatSheet(sheet,numDataRows){
  var totalCols=42;
  var dataStart=3;

  // Freeze rows and columns
  sheet.setFrozenRows(2);
  sheet.setFrozenColumns(2);

  // Row 1: Group headers
  sheet.getRange(1,1,1,totalCols).setFontWeight('bold').setFontColor('#FFFFFF').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sheet.setRowHeight(1,32);

  // Row 2: Column headers
  sheet.getRange(2,1,1,totalCols).setFontWeight('bold').setFontSize(9).setWrap(true)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sheet.setRowHeight(2,48);

  // Color the group header bands
  for(var g=0;g<COL_GROUPS.length;g++){
    var cg=COL_GROUPS[g];
    var startCol=cg[0],endCol=cg[1],darkClr=cg[2],lightClr=cg[3];
    var numCols=endCol-startCol+1;

    // Row 1 band
    sheet.getRange(1,startCol,1,numCols).setBackground(darkClr);
    // Row 2 band
    sheet.getRange(2,startCol,1,numCols).setBackground(darkClr).setFontColor('#FFFFFF');

    // Data rows: alternating light/white
    if(numDataRows>0){
      for(var r=0;r<numDataRows;r++){
        var bgColor=(r%2===0)?lightClr:'#FFFFFF';
        sheet.getRange(dataStart+r,startCol,1,numCols).setBackground(bgColor);
      }
    }
  }

  // Number formats
  var pctFmt='0.00%';
  if(numDataRows>0){
    sheet.getRange(dataStart,9,numDataRows,1).setNumberFormat(pctFmt);   // Forecast Accuracy
    sheet.getRange(dataStart,17,numDataRows,1).setNumberFormat(pctFmt);  // Dispatch %
    // Number format for qty columns
    var qtyFmt='#,##0';
    var qtyCols=[4,5,6,7,8,10,11,12,13,14,16,18,19,20,21,22,23,24,25,26,27,28];
    for(var q=0;q<qtyCols.length;q++){
      sheet.getRange(dataStart,qtyCols[q],numDataRows,1).setNumberFormat(qtyFmt);
    }
    // Finance columns: currency format
    var finFmt='#,##0';
    for(var f=34;f<=42;f++){
      sheet.getRange(dataStart,f,numDataRows,1).setNumberFormat(finFmt);
    }
  }

  // Column widths
  sheet.setColumnWidth(1,140);  // Item Group
  sheet.setColumnWidth(2,180);  // Item Code
  sheet.setColumnWidth(3,80);   // Product Class
  for(var c=4;c<=28;c++) sheet.setColumnWidth(c,90);
  sheet.setColumnWidth(29,180); // Sales Tag
  sheet.setColumnWidth(30,350); // Sales Narrative
  sheet.setColumnWidth(31,180); // Ops Tag
  sheet.setColumnWidth(32,350); // Ops Narrative
  sheet.setColumnWidth(33,300); // S&OP Alignment
  for(var c=34;c<=42;c++) sheet.setColumnWidth(c,100);

  // Data font
  if(numDataRows>0){
    sheet.getRange(dataStart,1,numDataRows,totalCols).setFontSize(9).setVerticalAlignment('middle');
  }
}
