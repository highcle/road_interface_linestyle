// エントリポイント: 初期化と画面全体の更新フロー
import { state, loadPrefs, savePrefs, readHash, writeHash } from './state.js';
import * as api from './api.js';
import * as time from './time.js';
import { initMap, setGeometry, restyle, highlightSelected, zoomTo, ensureVisible, map } from './roadmap.js';
import { initTimebar, setWindow, setModeLabel } from './timebar.js';
import { renderLegend, renderAlertList, renderDetail, hideDetail } from './panel.js';
import { updateConnector } from './connector.js';
import { initHistoryDialog, initImageDialog, initHelpDialog, initPlaceSearch } from './dialogs.js';

const AUTO_UPDATE_MS = 5 * 60 * 1000;
const el = (id) => document.getElementById(id);
let reqSeq = 0;
let lastFetchAt = 0;
let geometryReady = false;

// ---- 表示ユーティリティ ------------------------------------------------------
let loadingTimer = null;
function setLoading(on) {
  clearTimeout(loadingTimer);
  if (on) loadingTimer = setTimeout(() => { el('loadingIndicator').hidden = false; }, 250);
  else el('loadingIndicator').hidden = true;
}

function setStatus(text, isError = false) {
  const s = el('status');
  s.textContent = text;
  s.classList.toggle('error', isError);
}

function renderHeader(data) {
  const fresh = el('freshness');
  const now = time.parse(data.now);
  const gen = time.parse(data.generated_at);
  const latest = time.parse(data.latest_observation_at);
  if (data.mode === 'live') {
    const age = Math.max(0, Math.round((now - gen) / time.MIN));
    fresh.replaceChildren(
      Object.assign(document.createElement('span'), { textContent: `データ更新 ${time.short(gen, { withDate: false })}（${time.ageLabel(age)}）` }),
      Object.assign(document.createElement('span'), { className: 'muted', textContent: latest ? `最新観測 ${time.short(latest)}` : '観測なし' }),
    );
  } else {
    fresh.replaceChildren(Object.assign(document.createElement('span'), { textContent: '過去データを表示中' }));
  }
  fresh.classList.toggle('stale', Boolean(data.cache_stale));

  const stale = el('staleBanner');
  stale.hidden = !data.cache_stale;
  if (data.cache_stale) {
    const age = Math.round((now - gen) / time.MIN);
    stale.textContent = `⚠ データの更新が ${time.ageLabel(age).replace('前', '')}止まっています（最終更新 ${time.short(gen)}）。表示が実際の状況と異なる可能性があります。`;
  }

  const hb = el('historyBanner');
  hb.hidden = data.mode !== 'history';
  if (data.mode === 'history') {
    el('historyBannerText').textContent = `過去データ: ${time.rangeLabel(time.parse(data.window.start), time.parse(data.window.end))}`;
  }
  setModeLabel(data.mode === 'live' ? '直近24時間' : '検索期間');
  el('btnModeLive').setAttribute('aria-pressed', String(data.mode === 'live'));
  el('btnModeHistory').setAttribute('aria-pressed', String(data.mode === 'history'));
}

function renderAll() {
  restyle();
  renderLegend(onFilterChange);
  renderAlertList((id) => selectSegment(id, { zoom: true }));
  if (state.selectedId != null) showDetail(state.selectedId);
  updateConnector();
}

// ---- データ取得 --------------------------------------------------------------
async function load({ depth = 0 } = {}) {
  const seq = ++reqSeq;
  setLoading(true);
  try {
    const data = await api.fetchStatus({ history: state.mode === 'history' ? state.history : null, range: state.range });
    if (seq !== reqSeq) return;  // 後発のリクエストがあれば破棄
    lastFetchAt = Date.now();
    const win = { start: time.parse(data.window.start), end: time.parse(data.window.end) };
    const sameWin = state.window && state.window.start === win.start && state.window.end === win.end;
    if (!sameWin) setWindow(win);
    // スライダーの範囲が応答と違う（初回・期間の更新で調整された）場合は取り直す
    const r = { start: time.parse(data.range.start), end: time.parse(data.range.end) };
    if ((r.start !== state.range.start || r.end !== state.range.end) && depth < 1) {
      return load({ depth: depth + 1 });
    }
    state.status = data;
    renderHeader(data);
    if (geometryReady) renderAll();
    setStatus(`${data.counts.segments_with_data} 区間に観測あり`);
    writeHash(map);
  } catch (err) {
    if (seq !== reqSeq) return;
    console.error(err);
    setStatus(`更新できませんでした: ${err.message}`, true);
  } finally {
    if (seq === reqSeq) setLoading(false);
  }
}

// ---- 選択 --------------------------------------------------------------------
function showDetail(id) {
  const rep = state.status?.segments?.[id] ?? null;
  const timelinePromise = rep
    ? api.fetchTimeline(id, { history: state.mode === 'history' ? state.history : null, range: state.range })
        .then((d) => d.observations)
    : Promise.resolve([]);
  renderDetail(id, rep, { onImage: openImage, timelinePromise });
}

function selectSegment(id, { zoom = false } = {}) {
  state.selectedId = id;
  highlightSelected();
  showDetail(id);
  expandPanel();
  if (zoom) zoomTo(id);
  else ensureVisible(id);
  updateConnector();
  writeHash(map);
}

function clearSelection() {
  if (state.selectedId == null) return;
  state.selectedId = null;
  hideDetail();
  highlightSelected();
  updateConnector();
  writeHash(map);
}

function onFilterChange() {
  restyle();
  renderLegend(onFilterChange);
  renderAlertList((id) => selectSegment(id, { zoom: true }));
}

// ---- モード ------------------------------------------------------------------
function goLive() {
  state.mode = 'live';
  state.history = null;
  state.window = null;
  state.range = null;
  load();
}

function goHistory(range) {
  state.mode = 'history';
  state.history = range;
  state.window = null;
  state.range = null;
  load();
}

// ---- パネル開閉 ----------------------------------------------------------------
function expandPanel() {
  const panel = el('panel');
  panel.classList.remove('collapsed');
  el('btnPanelToggle').setAttribute('aria-expanded', 'true');
}

function initPanelToggle() {
  const panel = el('panel');
  const btn = el('btnPanelToggle');
  if (window.matchMedia('(max-width: 700px)').matches) {
    panel.classList.add('collapsed');
    btn.setAttribute('aria-expanded', 'false');
  }
  btn.addEventListener('click', () => {
    const collapsed = panel.classList.toggle('collapsed');
    btn.setAttribute('aria-expanded', String(!collapsed));
    updateConnector();
  });
}

let openImage = () => {};

// ---- 起動 --------------------------------------------------------------------
async function boot() {
  loadPrefs();
  const hash = readHash();
  if (hash.indicator) state.indicator = hash.indicator;
  if (hash.history) {
    state.mode = 'history';
    state.history = hash.history;
    state.range = hash.range;
  }

  initMap({
    view: hash.view,
    onSegmentClick: (id) => selectSegment(id),
    onBackgroundClick: clearSelection,
  });
  let hashTimer = null;
  map.on('move', updateConnector);
  map.on('moveend', () => { clearTimeout(hashTimer); hashTimer = setTimeout(() => writeHash(map), 300); });
  window.addEventListener('resize', updateConnector);
  el('panelBody').addEventListener('scroll', updateConnector, { passive: true });

  let sliderTimer = null;
  initTimebar(() => { clearTimeout(sliderTimer); sliderTimer = setTimeout(load, 150); });
  initPanelToggle();
  initHelpDialog();
  initPlaceSearch();
  openImage = initImageDialog();
  const historyDialog = initHistoryDialog(goHistory);

  el('btnModeLive').addEventListener('click', () => { if (state.mode !== 'live') goLive(); });
  el('btnModeHistory').addEventListener('click', () => historyDialog.open());
  el('btnBackToLive').addEventListener('click', goLive);
  el('btnCloseDetail').addEventListener('click', clearSelection);
  document.querySelectorAll('[data-indicator]').forEach((b) => b.addEventListener('click', () => {
    state.indicator = b.dataset.indicator;
    savePrefs();
    renderAll();
    writeHash(map);
  }));

  const auto = el('autoUpdate');
  auto.checked = state.autoUpdate;
  auto.addEventListener('change', () => {
    state.autoUpdate = auto.checked;
    savePrefs();
    if (auto.checked && state.mode === 'live') load();
  });
  setInterval(() => {
    if (state.autoUpdate && state.mode === 'live' && !document.hidden) load();
  }, AUTO_UPDATE_MS);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.autoUpdate && state.mode === 'live' && Date.now() - lastFetchAt > AUTO_UPDATE_MS) load();
  });

  // 道路形状（大きいがブラウザにキャッシュされる）と状態を並行取得
  setStatus('道路データを読み込み中…');
  const statusP = load();
  try {
    setGeometry(await api.fetchGeometry());
    geometryReady = true;
  } catch (err) {
    setStatus(`道路データを読み込めませんでした: ${err.message}`, true);
    return;
  }
  await statusP;
  if (state.status) renderAll();
  if (hash.seg != null) selectSegment(hash.seg, { zoom: !hash.view });
}

boot();
