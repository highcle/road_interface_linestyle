// 選択区間 → 詳細パネル を結ぶ引き出し線
import { state } from './state.js';
import { map, centerOf } from './roadmap.js';

const NS = 'http://www.w3.org/2000/svg';

export function updateConnector() {
  const svg = document.getElementById('svgOverlay');
  svg.replaceChildren();
  if (state.selectedId == null || !map) return;

  const panel = document.getElementById('panel');
  const detail = document.getElementById('detailPanel');
  // 狭い画面（パネルが下部シート）・パネルを畳んでいる・詳細が非表示 のときは描かない
  if (window.matchMedia('(max-width: 700px)').matches || panel.classList.contains('collapsed') || detail.hidden) return;

  const latlng = centerOf(state.selectedId);
  if (!latlng) return;
  const mapRect = document.getElementById('map').getBoundingClientRect();
  const p = map.latLngToContainerPoint(latlng);
  const sx = p.x + mapRect.left, sy = p.y + mapRect.top;
  // 区間が地図の表示範囲外なら描かない
  if (sx < mapRect.left || sx > mapRect.right || sy < mapRect.top || sy > mapRect.bottom) return;

  const head = detail.querySelector('.card-head').getBoundingClientRect();
  const panelRect = panel.getBoundingClientRect();
  const tx = panelRect.left;
  const ty = Math.min(Math.max(head.top + head.height / 2, panelRect.top + 12), panelRect.bottom - 12);
  if (sx >= tx) return;

  const path = document.createElementNS(NS, 'path');
  const mx = sx + (tx - sx) * 0.6;
  path.setAttribute('d', `M${sx} ${sy} C ${mx} ${sy}, ${mx} ${ty}, ${tx} ${ty}`);
  path.setAttribute('class', 'connector');
  const dot = document.createElementNS(NS, 'circle');
  dot.setAttribute('cx', sx); dot.setAttribute('cy', sy); dot.setAttribute('r', 5);
  dot.setAttribute('class', 'connector-dot');
  svg.append(path, dot);
}
