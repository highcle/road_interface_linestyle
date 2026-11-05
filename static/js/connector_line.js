/**
 * 地図上の選択セグメント中心から右側パネルへ矢印線を描画
 */
function updateConnectorLine() {
  const svg = document.getElementById('svgOverlay');
  svg.innerHTML = '';

  if (!AppState.selectedLatLng || !AppState.selectedFeature) return;

  const mapEl = document.getElementById('map');
  const panel = document.getElementById('detailPanel');
  if (!mapEl || !panel || panel.style.display === 'none') return;

  // 1. 地図コンテナとパネルの位置情報を取得
  const mapRect = mapEl.getBoundingClientRect();
  const panelRect = panel.getBoundingClientRect();

  // 2. 緯度経度を #map 基準のピクセル座標に変換
  const containerPoint = AppState.map.latLngToContainerPoint(AppState.selectedLatLng);

  // 3. ビューポート全体の絶対座標へ変換 (#map の表示位置オフセットを加算)
  const startX = containerPoint.x + mapRect.left;
  const startY = containerPoint.y + mapRect.top;

  // 4. パネルの左縁・上下中央の座標を取得
  const targetX = panelRect.left;
  const targetY = panelRect.top + (panelRect.height / 2);

  // 5. SVG マーカー（矢印頭）の定義
  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  defs.innerHTML = `
    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#0055ff" />
    </marker>
  `;
  svg.appendChild(defs);

  // 6. 矢印線の描画
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('x1', startX);
  line.setAttribute('y1', startY);
  line.setAttribute('x2', targetX);
  line.setAttribute('y2', targetY);
  line.setAttribute('stroke', '#0055ff');
  line.setAttribute('stroke-width', '3');
  line.setAttribute('stroke-dasharray', '6,4');
  line.setAttribute('marker-end', 'url(#arrowhead)');

  svg.appendChild(line);
}

function clearConnectorLine() {
  const svg = document.getElementById('svgOverlay');
  svg.innerHTML = '';
}