// ダイアログ（過去検索・画像拡大・ヘルプ）
import { state } from './state.js';
import * as time from './time.js';
import { surfaceLabel } from './categories.js';

const MAX_DAYS = window.APP_CONFIG.maxSearchDays;
const el = (id) => document.getElementById(id);

// <dialog> の背景クリックで閉じる
function closeOnBackdrop(dlg) {
  dlg.addEventListener('click', (e) => {
    const r = dlg.getBoundingClientRect();
    const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    if (!inside) dlg.close();
  });
}

// ---- 過去検索 ---------------------------------------------------------------
export function initHistoryDialog(onSearch) {
  const dlg = el('historyDialog');
  closeOnBackdrop(dlg);
  el('maxDaysLabel').textContent = MAX_DAYS;
  el('btnHistoryCancel').addEventListener('click', () => dlg.close());

  const setInputs = (s, e) => { el('historyStart').value = time.toInput(s); el('historyEnd').value = time.toInput(e); };
  dlg.querySelectorAll('[data-preset]').forEach((b) => b.addEventListener('click', () => {
    const now = nowMs();
    const today0 = time.parse(time.format(now).slice(0, 10) + ' 00:00:00');
    const p = b.dataset.preset;
    if (p === 'today') setInputs(today0, now);
    if (p === 'yesterday') setInputs(today0 - time.DAY, today0);
    if (p === 'last3days') setInputs(now - 3 * time.DAY, now);
    if (p === 'lastweek') setInputs(now - 7 * time.DAY - 3 * time.HOUR, now - 7 * time.DAY + 3 * time.HOUR);
    validate();
  }));

  const validate = () => {
    const s = time.parse(el('historyStart').value), e = time.parse(el('historyEnd').value);
    let msg = '';
    if (s == null || e == null) msg = '開始日時と終了日時を入力してください。';
    else if (s >= e) msg = '開始日時は終了日時より前にしてください。';
    else if (e - s > MAX_DAYS * time.DAY) msg = `検索期間は最大 ${MAX_DAYS} 日間です。`;
    else if (s > nowMs()) msg = '未来の日時は検索できません。';
    el('historyError').textContent = msg;
    el('historyError').hidden = !msg;
    el('btnHistorySearch').disabled = Boolean(msg);
    return msg ? null : { start: s, end: Math.min(e, nowMs()) };
  };
  el('historyStart').addEventListener('input', validate);
  el('historyEnd').addEventListener('input', validate);

  el('historyForm').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const r = validate();
    if (!r) return;
    dlg.close();
    onSearch(r);
  });

  return {
    open() {
      const now = nowMs();
      const base = state.history || { start: now - 3 * time.HOUR, end: now };
      setInputs(base.start, base.end);
      el('historyEnd').max = time.toInput(now);
      el('historyStart').max = time.toInput(now);
      validate();
      dlg.showModal();
    },
  };
}

/** サーバー基準の現在時刻（ブラウザ時計ではなく、最後に取得したステータスの now） */
function nowMs() {
  return time.parse(state.status?.now) ?? state.window?.end ?? time.fallbackNow();
}

// ---- 画像拡大 ---------------------------------------------------------------
export function initImageDialog() {
  const dlg = el('imageDialog');
  closeOnBackdrop(dlg);
  return (rep) => {
    el('imageDialogImg').src = rep.image_url;
    el('imageDialogImg').alt = `${rep.observed_at} の路面画像`;
    el('imageDialogCaption').textContent =
      `${rep.observed_at} / WIPS ${rep.wips != null ? rep.wips.toFixed(2) : '欠損'} / 路面 ${surfaceLabel(rep.road_surface)}`;
    dlg.showModal();
  };
}

// ---- ヘルプ -----------------------------------------------------------------
export function initHelpDialog() {
  const dlg = el('helpDialog');
  closeOnBackdrop(dlg);
  const T = window.APP_CONFIG.thresholds;
  dlg.querySelectorAll('.th-warn').forEach((n) => { n.textContent = T.warn.toFixed(1); });
  dlg.querySelectorAll('.th-danger').forEach((n) => { n.textContent = T.danger.toFixed(1); });
  el('btnHelp').addEventListener('click', () => dlg.showModal());
}
