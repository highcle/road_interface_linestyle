// 時間スライダー
// 範囲はサーバーから受け取った「データの期間」(state.window) に合わせる。
// ブラウザの時計は使わない（端末の時刻ずれ・タイムゾーンの影響を受けないため）。
import { state } from './state.js';
import * as time from './time.js';

const STEP = 5 * time.MIN;
let slider = null;
let onChange = () => {};

export function initTimebar(handler) {
  onChange = handler;
  slider = document.getElementById('timeSlider');
  const now = Date.now();
  noUiSlider.create(slider, {
    start: [now - time.HOUR, now],
    connect: true,
    range: { min: now - time.DAY, max: now },
    step: STEP,
    behaviour: 'tap-drag',
    handleAttributes: [{ 'aria-label': '表示開始時刻' }, { 'aria-label': '表示終了時刻' }],
  });
  slider.setAttribute('disabled', true);
  slider.noUiSlider.on('update', (vals) => updateLabel(Number(vals[0]), Number(vals[1])));
  slider.noUiSlider.on('change', (vals) => {
    state.range = { start: Number(vals[0]), end: Number(vals[1]) };
    markPreset();
    onChange();
  });

  document.querySelectorAll('#timeBar [data-hours]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!state.window) return;
      const h = btn.dataset.hours;
      const end = state.window.end;
      const start = h === 'all' ? state.window.start : Math.max(state.window.start, end - Number(h) * time.HOUR);
      setRange({ start, end });
      onChange();
    });
  });
}

function pipFormatter(win) {
  const multiDay = win.end - win.start > 1.5 * time.DAY;
  return {
    to(v) {
      const d = new Date(v);
      const midnight = d.getUTCHours() === 0 && d.getUTCMinutes() === 0;
      return multiDay || midnight || v === win.start ? time.short(v) : time.short(v, { withDate: false });
    },
  };
}

/** データ期間が変わったとき（自動更新・過去検索）に呼ぶ。 */
export function setWindow(win, { keepEndAtLatest = true } = {}) {
  const prevWin = state.window;
  const prevRange = state.range;
  state.window = win;
  let range;
  if (!prevWin && prevRange && prevRange.start >= win.start && prevRange.end <= win.end) {
    range = prevRange;  // URL で共有された範囲
  } else if (!prevRange || !prevWin) {
    range = { start: Math.max(win.start, win.end - 6 * time.HOUR), end: win.end };
  } else if (keepEndAtLatest && prevRange.end >= prevWin.end - STEP) {
    // 右端に張り付いていたら最新に追従（幅は維持）
    const width = prevRange.end - prevRange.start;
    range = { start: Math.max(win.start, win.end - width), end: win.end };
  } else {
    range = { start: Math.max(win.start, prevRange.start), end: Math.min(win.end, prevRange.end) };
    if (range.start >= range.end) range = { start: win.start, end: win.end };
  }
  const narrow = window.matchMedia('(max-width: 700px)').matches;
  slider.noUiSlider.updateOptions({
    range: { min: win.start, max: win.end },
    pips: { mode: 'count', values: narrow ? 4 : 7, density: 4, stepped: false, format: pipFormatter(win) },
  }, false);
  slider.removeAttribute('disabled');
  setRange(range);
}

export function setRange(range) {
  state.range = range;
  slider.noUiSlider.set([range.start, range.end], false);
  updateLabel(range.start, range.end);
  markPreset();
}

function updateLabel(start, end) {
  document.getElementById('timeRangeLabel').textContent =
    `${time.rangeLabel(start, end)}（${time.durationLabel(end - start)}）`;
}

function markPreset() {
  const r = state.range, w = state.window;
  document.querySelectorAll('#timeBar [data-hours]').forEach((btn) => {
    const h = btn.dataset.hours;
    const atEnd = r && w && r.end === w.end;
    const on = atEnd && (h === 'all' ? r.start === w.start
      : r.end - r.start === Number(h) * time.HOUR || (r.start === w.start && w.end - w.start < Number(h) * time.HOUR));
    btn.setAttribute('aria-pressed', String(Boolean(on)));
  });
}

export function setModeLabel(text) {
  document.getElementById('timeModeLabel').textContent = text;
}
