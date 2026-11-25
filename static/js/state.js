// アプリ全体の状態と、URL ハッシュ / localStorage への保存
import { INDICATORS } from './categories.js';

const STORAGE_KEY = 'winterroad.linestyle.v2';

function defaultFilters() {
  const f = {};
  for (const ind of Object.values(INDICATORS)) for (const c of ind.classes) f[c.key] = true;
  f.nodata = true;
  return f;
}

export const state = {
  mode: 'live',            // 'live' | 'history'
  indicator: 'wips',       // 'wips' | 'surface'
  filters: defaultFilters(),
  window: null,            // { start, end } ms: データの全期間（現在=直近24h、過去=検索期間）
  range: null,             // { start, end } ms: スライダーで選んだ表示範囲
  history: null,           // { start, end } ms: 過去検索の期間
  status: null,            // /api/roads/status の結果
  selectedId: null,
  autoUpdate: true,
  gradient: true,          // 線を隣の区間となめらかにつなぐ
  showBuses: true,         // バスの現在位置を表示
};

export function loadPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (saved.indicator in INDICATORS) state.indicator = saved.indicator;
    if (saved.filters) Object.assign(state.filters, saved.filters);
    if (typeof saved.autoUpdate === 'boolean') state.autoUpdate = saved.autoUpdate;
    if (typeof saved.gradient === 'boolean') state.gradient = saved.gradient;
    if (typeof saved.showBuses === 'boolean') state.showBuses = saved.showBuses;
  } catch { /* 破損時は既定値 */ }
}

export function savePrefs() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      indicator: state.indicator, filters: state.filters, autoUpdate: state.autoUpdate,
      gradient: state.gradient, showBuses: state.showBuses,
    }));
  } catch { /* プライベートモード等 */ }
}

/** URL ハッシュ: #map=zoom/lat/lng&ind=wips&seg=123&hist=start~end&range=start~end */
export function readHash() {
  const out = {};
  const params = new URLSearchParams(location.hash.slice(1));
  const m = (params.get('map') || '').split('/').map(Number);
  if (m.length === 3 && m.every(Number.isFinite)) out.view = { zoom: m[0], lat: m[1], lng: m[2] };
  if (params.get('ind') in INDICATORS) out.indicator = params.get('ind');
  const seg = Number(params.get('seg'));
  if (params.has('seg') && Number.isInteger(seg)) out.seg = seg;
  const parsePair = (v) => {
    const [a, b] = (v || '').split('~').map(Number);
    return Number.isFinite(a) && Number.isFinite(b) && a < b ? { start: a, end: b } : null;
  };
  out.history = parsePair(params.get('hist'));
  out.range = parsePair(params.get('range'));
  return out;
}

export function writeHash(map) {
  const params = new URLSearchParams();
  const c = map.getCenter();
  params.set('map', `${map.getZoom()}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`);
  params.set('ind', state.indicator);
  if (state.selectedId != null) params.set('seg', state.selectedId);
  if (state.mode === 'history' && state.history) {
    params.set('hist', `${state.history.start}~${state.history.end}`);
    if (state.range) params.set('range', `${state.range.start}~${state.range.end}`);
  }
  history.replaceState(null, '', `#${params.toString().replace(/%7E/gi, '~').replace(/%2F/gi, '/')}`);
}
