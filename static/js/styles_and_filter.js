function getCategoryKey(feature) {
  const mode = document.getElementById('modeSelect').value;
  const props = feature.properties;
  const hasData = props.wips !== null && props.wips !== undefined;

  if (mode === 'wips') {
    if (!hasData) return 'wips_none';
    if (props.wips <= 7.5) return 'wips_danger';
    if (props.wips < 8.0) return 'wips_warn';
    return 'wips_good';
  } else {
    if (!props.road_surface) return 'surface_none';
    const s = String(props.road_surface).toLowerCase();
    if (s.includes('ice') || s.includes('凍結')) return 'ice';
    if (s.includes('slush') || s.includes('スラッシュ') || s.includes('シャーベット')) return 'slush'; // ★ Slush追加
    if (s.includes('semi-wet') || s.includes('半湿潤')) return 'semi_wet';
    if (s.includes('fresh') || s.includes('snow') || s.includes('新雪') || s.includes('圧雪')) return 'fresh';
    if (s.includes('wet') || s.includes('湿潤')) return 'wet';
    if (s.includes('dry') || s.includes('乾燥')) return 'dry';
    return 'other';
  }
}

function getFeatureStyle(feature, currentStartStr, currentEndStr) {
  const mode = document.getElementById('modeSelect').value;
  const props = feature.properties;
  const catKey = getCategoryKey(feature);
  
  // ★ クライアント側での時間フィルタリング判定
  let inTimeRange = true;
  if (props.last_updated && currentStartStr && currentEndStr) {
    if (props.last_updated < currentStartStr || props.last_updated > currentEndStr) {
      inTimeRange = false;
    }
  }

  const hasData = props.wips !== null && props.wips !== undefined && inTimeRange;

  // 非表示チェックボックス判定 または 時間外の場合
  if (AppState.visibleFilters[catKey] === false || (!hasData && props.wips !== null)) {
    // 時間範囲外のデータは「データなし（灰色・細線）」として扱う
    if (!inTimeRange && AppState.visibleFilters['wips_none'] === false) {
      return { opacity: 0, weight: 0 };
    }
  }

  const weight = hasData ? 10 : 3;
  const opacity = hasData ? 0.9 : 0.3;

  let color = '#888888';

  if (hasData) {
    if (mode === 'wips') {
      if (catKey === 'wips_danger') color = '#d7191c';
      else if (catKey === 'wips_warn') color = '#fdae61';
      else if (catKey === 'wips_good') color = '#2c7bb6';
    } else {
      if (catKey === 'ice') color = '#9000ff';         // 凍結: 紫
      else if (catKey === 'slush') color = '#d35400';   // ★ Slush: 濃いオレンジ/茶
      else if (catKey === 'semi_wet') color = '#00a896'; // 半湿潤: シアン
      else if (catKey === 'fresh') color = '#00bfff';    // 新雪: 水色
      else if (catKey === 'wet') color = '#2c7bb6';      // 湿潤: 青
      else if (catKey === 'dry') color = '#2ca02c';      // 乾燥: 緑
      else if (catKey === 'other') color = '#ff7f0e';
    }
  }

  return { color: color, weight: weight, opacity: opacity, lineCap: 'round', lineJoin: 'round' };
}

function updateLegend() {
  const mode = document.getElementById('modeSelect').value;
  const legendArea = document.getElementById('legendArea');
  
  if (mode === 'wips') {
    legendArea.innerHTML = `
      <b>WIPS フィルタ / 凡例</b>
      <div class="legend-item"><input type="checkbox" id="cb_wips_good" ${AppState.visibleFilters.wips_good ? 'checked' : ''} onchange="toggleFilter('wips_good')"><div class="color-box" style="background:#2c7bb6;"></div>8.0 以上: 良好</div>
      <div class="legend-item"><input type="checkbox" id="cb_wips_warn" ${AppState.visibleFilters.wips_warn ? 'checked' : ''} onchange="toggleFilter('wips_warn')"><div class="color-box" style="background:#fdae61;"></div>7.5超 - 8.0未満: 注意</div>
      <div class="legend-item"><input type="checkbox" id="cb_wips_danger" ${AppState.visibleFilters.wips_danger ? 'checked' : ''} onchange="toggleFilter('wips_danger')"><div class="color-box" style="background:#d7191c;"></div>7.5 以下: 危険</div>
      <div class="legend-item"><input type="checkbox" id="cb_wips_none" ${AppState.visibleFilters.wips_none ? 'checked' : ''} onchange="toggleFilter('wips_none')"><div class="color-box" style="background:#888888; height:3px;"></div>データなし (細線)</div>
    `;
  } else {
    legendArea.innerHTML = `
      <b>路面状態 フィルタ / 凡例</b>
      <div class="legend-item"><input type="checkbox" id="cb_dry" ${AppState.visibleFilters.dry ? 'checked' : ''} onchange="toggleFilter('dry')"><div class="color-box" style="background:#2ca02c;"></div>Dry (乾燥)</div>
      <div class="legend-item"><input type="checkbox" id="cb_wet" ${AppState.visibleFilters.wet ? 'checked' : ''} onchange="toggleFilter('wet')"><div class="color-box" style="background:#2c7bb6;"></div>Wet (湿潤)</div>
      <div class="legend-item"><input type="checkbox" id="cb_semi_wet" ${AppState.visibleFilters.semi_wet ? 'checked' : ''} onchange="toggleFilter('semi_wet')"><div class="color-box" style="background:#00a896;"></div>Semi-Wet (半湿潤)</div>
      <div class="legend-item"><input type="checkbox" id="cb_fresh" ${AppState.visibleFilters.fresh ? 'checked' : ''} onchange="toggleFilter('fresh')"><div class="color-box" style="background:#00bfff;"></div>Fresh (新雪/積雪)</div>
      <div class="legend-item"><input type="checkbox" id="cb_slush" ${AppState.visibleFilters.slush ? 'checked' : ''} onchange="toggleFilter('slush')"><div class="color-box" style="background:#d35400;"></div>Slush (スラッシュ)</div>
      <div class="legend-item"><input type="checkbox" id="cb_ice" ${AppState.visibleFilters.ice ? 'checked' : ''} onchange="toggleFilter('ice')"><div class="color-box" style="background:#9000ff;"></div>Ice (凍結)</div>
      <div class="legend-item"><input type="checkbox" id="cb_surface_none" ${AppState.visibleFilters.surface_none ? 'checked' : ''} onchange="toggleFilter('surface_none')"><div class="color-box" style="background:#888888; height:3px;"></div>データなし (細線)</div>
    `;
  }
}

function toggleFilter(key) {
  AppState.visibleFilters[key] = !AppState.visibleFilters[key];
  refreshLayerStyles();
}

function onModeChange() {
  refreshLayerStyles();
  updateLegend();
}