// 地図と道路レイヤー
import { state } from './state.js';
import { INDICATORS, COLORS, freshnessOpacity, levelColor } from './categories.js';

export let map = null;
let roadLayer = null;
let highlightLayer = null;
const layersById = new Map();
let onSelect = () => {};

const HOKKAIDO = L.latLngBounds([41.3, 139.3], [45.6, 145.9]);

// ---- グラデーション表示 -------------------------------------------------------
// 区間の両端（隣の区間と共有する点＝ノード）に、つながっている区間の値の平均を与え、
// 「始点ノードの色 → 区間自身の色（中央） → 終点ノードの色」と塗る。
// 区間の中央は必ず区間自身の区分の色になり、つなぎ目では隣り合う区間が同じ色になる。
const ends = new Map();    // 区間ID → [始点ノード, 終点ノード]
const nodes = new Map();   // ノード → [区間ID...]
let gradients = new Map(); // 区間ID → [[位置, 色], ...]

/** Canvas で線をグラデーションで描く（options.gradient があれば strokeStyle に使う） */
const GradientCanvas = L.Canvas.extend({
  _fillStroke(ctx, layer) {
    const stops = layer.options.gradient;
    const rings = layer._rings;
    if (stops && rings && rings.length && rings[0].length) {
      const a = rings[0][0];
      const lastRing = rings[rings.length - 1];
      const b = lastRing[lastRing.length - 1];
      if (a.x !== b.x || a.y !== b.y) {
        const g = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
        for (const [t, c] of stops) g.addColorStop(t, c);
        const color = layer.options.color;
        layer.options.color = g;
        try { L.Canvas.prototype._fillStroke.call(this, ctx, layer); } finally { layer.options.color = color; }
        return;
      }
    }
    L.Canvas.prototype._fillStroke.call(this, ctx, layer);
  },
});

/** 表示中（フィルタで隠れていない）の区間の区分レベル。色を持たない区間は null */
function levelOf(id) {
  const rep = repFor(id);
  if (!rep) return null;
  const ind = INDICATORS[state.indicator];
  const key = ind.classify(rep);
  if (state.filters[key] === false) return null;
  const level = ind.classes.find((c) => c.key === key)?.level ?? -1;
  return level >= 0 ? level : null;
}

function computeGradients() {
  gradients = new Map();
  if (!state.gradient || !state.status) return;
  const levels = new Map();
  for (const k of Object.keys(state.status.segments || {})) {
    const lv = levelOf(Number(k));
    if (lv != null) levels.set(Number(k), lv);
  }
  const nodeLevel = new Map();
  const levelAtNode = (node) => {
    if (nodeLevel.has(node)) return nodeLevel.get(node);
    let sum = 0, n = 0;
    for (const id of nodes.get(node) || []) if (levels.has(id)) { sum += levels.get(id); n += 1; }
    const v = n ? sum / n : null;
    nodeLevel.set(node, v);
    return v;
  };
  const STEPS = 8;
  for (const [id, own] of levels) {
    const [s, e] = ends.get(id) || [];
    const a = levelAtNode(s) ?? own;
    const b = levelAtNode(e) ?? own;
    if (a === own && b === own) continue;  // 両端とも同じ → 単色
    const stops = [];
    for (let i = 0; i <= STEPS; i += 1) {
      const t = i / STEPS;
      const lv = t <= 0.5 ? a + (own - a) * (t / 0.5) : own + (b - own) * ((t - 0.5) / 0.5);
      stops.push([t, levelColor(state.indicator, lv)]);
    }
    gradients.set(id, stops);
  }
}

export function initMap({ view, onSegmentClick, onBackgroundClick }) {
  onSelect = onSegmentClick;
  map = L.map('map', {
    preferCanvas: true,          // 数万本の線を軽く描くため Canvas を使う
    renderer: new GradientCanvas({ tolerance: 6, padding: 0.3 }),  // 細い線でもクリックしやすく
    zoomControl: false,
    minZoom: 6,
    maxBounds: HOKKAIDO.pad(0.5),
  });
  L.control.zoom({ position: 'bottomleft', zoomInTitle: '拡大', zoomOutTitle: '縮小' }).addTo(map);
  L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">国土地理院</a>',
  }).addTo(map);
  // 区間の路線名・市町村（scripts/build_road_attributes.py）の出典
  map.attributionControl.addAttribution(
    '道路: 国土数値情報（道路・行政区域） / 路線名: © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors');
  map.createPane('highlight').style.zIndex = 450;

  if (view) map.setView([view.lat, view.lng], view.zoom);
  else map.fitBounds(HOKKAIDO);

  map.on('click', onBackgroundClick);
  map.on('zoomend', restyle);
  addLocateControl();
  return map;
}

function addLocateControl() {
  const Locate = L.Control.extend({
    options: { position: 'bottomleft' },
    onAdd() {
      const btn = L.DomUtil.create('button', 'leaflet-bar locate-btn');
      btn.type = 'button';
      btn.title = '現在地へ移動';
      btn.setAttribute('aria-label', '現在地へ移動');
      btn.textContent = '◎';
      L.DomEvent.disableClickPropagation(btn);
      btn.addEventListener('click', () => map.locate({ setView: true, maxZoom: 13 }));
      return btn;
    },
  });
  new Locate().addTo(map);
  let marker = null;
  map.on('locationfound', (e) => {
    marker?.remove();
    marker = L.circleMarker(e.latlng, { radius: 7, color: '#fff', weight: 2, fillColor: '#1a73e8', fillOpacity: 1 })
      .addTo(map).bindTooltip('現在地');
  });
  map.on('locationerror', () => alert('現在地を取得できませんでした。位置情報の利用を許可してください。'));
}

export function setGeometry(geojson) {
  roadLayer = L.geoJSON(geojson, {
    style: styleFor,
    onEachFeature(feature, layer) {
      const id = feature.properties.id;
      layersById.set(id, layer);
      const c = feature.geometry?.coordinates || [];
      if (c.length >= 2) {
        const key = (p) => `${p[0]},${p[1]}`;
        const se = [key(c[0]), key(c[c.length - 1])];
        ends.set(id, se);
        for (const k of se) {
          if (!nodes.has(k)) nodes.set(k, []);
          nodes.get(k).push(id);
        }
      }
      layer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        onSelect(feature.properties.id, e.latlng);
      });
    },
  }).addTo(map);
}

export const getLayer = (id) => layersById.get(id);
export const repFor = (id) => state.status?.segments?.[id] ?? null;

function baseWeight() {
  const z = map.getZoom();
  return z <= 8 ? 2.5 : z <= 10 ? 4 : z <= 13 ? 6 : 8;
}

export function categoryOf(id) {
  const rep = repFor(id);
  return rep ? INDICATORS[state.indicator].classify(rep) : null;
}

function styleFor(feature) {
  const id = feature.properties.id;
  const rep = repFor(id);
  const w = baseWeight();
  if (!rep) {
    if (!state.filters.nodata) return { opacity: 0, weight: 0, interactive: false, gradient: null };
    return { color: COLORS.none, weight: Math.max(1.5, w * 0.35), opacity: 0.35, interactive: true, gradient: null };
  }
  const ind = INDICATORS[state.indicator];
  const key = ind.classify(rep);
  if (state.filters[key] === false) return { opacity: 0, weight: 0, interactive: false, gradient: null };
  const cls = ind.classes.find((c) => c.key === key);
  const severe = ind.isAlert(key) ? 1.5 : 0;
  return {
    color: cls.color,
    weight: w + severe,
    opacity: freshnessOpacity(rep.age_minutes),
    lineCap: 'round',
    lineJoin: 'round',
    interactive: true,
    gradient: gradients.get(id) || null,
  };
}

export function restyle() {
  if (!roadLayer) return;
  computeGradients();
  roadLayer.setStyle(styleFor);
  // 観測のある区間を上に描く（灰色線に埋もれないように）
  for (const id of Object.keys(state.status?.segments || {})) layersById.get(Number(id))?.bringToFront();
  highlightSelected();
}

export function highlightSelected() {
  highlightLayer?.remove();
  highlightLayer = null;
  const layer = state.selectedId != null ? layersById.get(state.selectedId) : null;
  if (!layer) return;
  const feature = layer.feature;
  const st = styleFor(feature);
  highlightLayer = L.layerGroup([
    L.geoJSON(feature, { pane: 'highlight', interactive: false,
      style: { color: '#111', weight: baseWeight() + 8, opacity: 0.85, lineCap: 'round' } }),
    L.geoJSON(feature, { pane: 'highlight', interactive: false,
      style: { color: '#fff', weight: baseWeight() + 4, opacity: 1, lineCap: 'round' } }),
    L.geoJSON(feature, { pane: 'highlight', interactive: false,
      style: { color: st.color || COLORS.none, weight: baseWeight() + 1, opacity: 1, lineCap: 'round' } }),
  ]).addTo(map);
}

export function centerOf(id) {
  const layer = layersById.get(id);
  if (!layer) return null;
  const latlngs = layer.getLatLngs().flat(Infinity);
  return latlngs[Math.floor(latlngs.length / 2)] || layer.getBounds().getCenter();
}

export function zoomTo(id) {
  const layer = layersById.get(id);
  if (!layer) return;
  // パネルに隠れない位置に収める（狭い画面では下部シート、広い画面では右パネル）
  const panel = document.getElementById('panel');
  const mapRect = map.getContainer().getBoundingClientRect();
  const pr = panel.classList.contains('collapsed') ? null : panel.getBoundingClientRect();
  const narrow = window.matchMedia('(max-width: 700px)').matches;
  const padBR = !pr ? [40, 40] : narrow
    ? [40, Math.max(40, mapRect.bottom - pr.top + 30)]
    : [Math.max(40, mapRect.right - pr.left + 30), 40];
  map.flyToBounds(layer.getBounds(), { maxZoom: 15, paddingTopLeft: [40, 60], paddingBottomRight: padBR, duration: 0.6 });
}

/** 選択区間がパネルの下に隠れていたら、見える位置まで地図をずらす */
export function ensureVisible(id) {
  const c = centerOf(id);
  const panel = document.getElementById('panel');
  if (!c || panel.classList.contains('collapsed')) return;
  const mapRect = map.getContainer().getBoundingClientRect();
  const pr = panel.getBoundingClientRect();
  const pt = map.latLngToContainerPoint(c);
  const narrow = window.matchMedia('(max-width: 700px)').matches;
  if (narrow) {
    const visibleBottom = pr.top - mapRect.top - 30;
    if (pt.y > visibleBottom) map.panBy([0, pt.y - visibleBottom / 2], { duration: 0.4 });
  } else {
    const visibleRight = pr.left - mapRect.left - 30;
    if (pt.x > visibleRight) map.panBy([pt.x - visibleRight / 2, 0], { duration: 0.4 });
  }
}
