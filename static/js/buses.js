// バスの現在位置（観測時刻が5分以内の最新観測）
// サーバーが「車両ごとの最新1点」「近い点は最新の1点にまとめる」処理をした結果を表示する。
import { state } from './state.js';
import * as api from './api.js';
import * as time from './time.js';
import { map } from './roadmap.js';
import { surfaceLabel } from './categories.js';

const REFRESH_MS = 60 * 1000;
const el = (id) => document.getElementById(id);
let layer = null;
let seq = 0;
let onImage = () => {};

export function initBuses({ onImageClick }) {
  onImage = onImageClick;
  map.createPane('buses').style.zIndex = 620;  // 道路・強調表示より上、ツールチップより下
  // 縮小表示では小さくして、周りの道路の線を覆わないようにする
  const resize = () => map.getContainer().classList.toggle('buses-small', map.getZoom() <= 9);
  map.on('zoomend', resize);
  resize();
  layer = L.layerGroup().addTo(map);
  setInterval(() => { if (!document.hidden) refreshBuses(); }, REFRESH_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshBuses(); });
}

export async function refreshBuses() {
  const s = ++seq;
  if (state.mode !== 'live') {  // 過去データの表示中は出さない
    layer.clearLayers();
    return;
  }
  try {
    const data = await api.fetchBuses();
    if (s !== seq || state.mode !== 'live') return;
    render(data);
  } catch (err) {
    if (s !== seq) return;
    console.warn('バスの位置を取得できませんでした', err);
  }
}

function busIcon(b) {
  const root = document.createElement('div');
  root.className = 'bus-marker';
  if (b.heading != null) {
    const arrow = document.createElement('span');
    arrow.className = 'bus-heading';
    arrow.style.transform = `rotate(${b.heading}deg)`;
    root.append(arrow);
  }
  const body = document.createElement('span');
  body.className = 'bus-body';
  body.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6 2h12a3 3 0 0 1 3 3v11a2 2 0 0 1-1 1.73V20a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1v-2H7v2a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2.27A2 2 0 0 1 3 16V5a3 3 0 0 1 3-3Zm0 3v6h12V5H6Zm1.5 8.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Zm9 0a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z"/></svg>';
  root.append(body);
  return L.divIcon({ html: root, className: 'bus-icon', iconSize: [30, 30], iconAnchor: [15, 15] });
}

function tooltipText(b) {
  const lines = [
    `${time.short(time.parse(b.observed_at))}（${b.age_seconds < 60 ? `${b.age_seconds}秒前` : time.ageLabel(Math.floor(b.age_seconds / 60))}）`,
    `WIPS ${b.wips != null ? b.wips.toFixed(2) : '欠損'} / 路面 ${surfaceLabel(b.road_surface)}`,
  ];
  // 車両番号は管理用の呼び名なので表示しない
  if (b.merged.length) lines.push(`近くにいる他の ${b.merged.length} 台もまとめて表示`);
  return lines.join('\n');
}

function render(data) {
  layer.clearLayers();
  for (const b of data.buses) {
    const m = L.marker([b.lat, b.lon], {
      icon: busIcon(b), pane: 'buses', keyboard: true,
      title: 'バスの現在位置', alt: 'バスの現在位置',
    });
    m.bindTooltip(tooltipText(b), { direction: 'top', offset: [0, -14], className: 'bus-tooltip' });
    if (b.image_url) m.on('click', () => onImage(b));
    layer.addLayer(m);
  }
}
