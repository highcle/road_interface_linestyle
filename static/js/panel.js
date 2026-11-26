// 右パネル: 凡例/フィルタ、注意区間一覧、選択区間の詳細
import { state, savePrefs } from './state.js';
import { INDICATORS, COLORS, classInfo, surfaceLabel } from './categories.js';
import { categoryOf, getLayer, lengthOf } from './roadmap.js';
import { groupAlerts, lengthLabel } from './alerts.js';
import * as time from './time.js';

const T = window.APP_CONFIG.thresholds;
const el = (id) => document.getElementById(id);

/** DOM 要素を作る小さなヘルパー（innerHTML を使わず、値は textContent で入れる） */
function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'style') node.style.cssText = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) node.append(c instanceof Node ? c : String(c));
  return node;
}

// ---- 凡例 / フィルタ ------------------------------------------------------
export function renderLegend(onFilterChange) {
  const ind = INDICATORS[state.indicator];
  const counts = {};
  let total = 0;
  for (const id of Object.keys(state.status?.segments || {})) {
    const k = categoryOf(Number(id));
    counts[k] = (counts[k] || 0) + 1;
    total += 1;
  }
  const rows = [...ind.classes].reverse().filter((c) => !c.dataless || counts[c.key]);
  const make = (key, label, color, count, thin) => h('label', { class: 'legend-item' },
    h('input', {
      type: 'checkbox', checked: state.filters[key] !== false,
      onchange: (e) => { state.filters[key] = e.target.checked; savePrefs(); onFilterChange(); },
    }),
    h('span', { class: `sw${thin ? ' sw-thin' : ''}`, style: `--c:${color}` }),
    h('span', { class: 'legend-label' }, label),
    h('span', { class: 'legend-count' }, count != null ? `${count}` : ''),
  );
  const list = h('div', { class: 'legend-list' },
    rows.map((c) => make(c.key, c.label, c.color, counts[c.key] || 0)),
    make('nodata', '期間内に観測なし', COLORS.none, null, true),
  );
  const order = state.indicator === 'surface'
    ? h('p', { class: 'legend-order' }, '↑ 滑りやすい　↓ 滑りにくい')
    : h('p', { class: 'legend-order' }, '↑ 視界が悪い　↓ 視界が良い');
  el('legendArea').replaceChildren(order, list,
    h('p', { class: 'legend-total' }, `観測のある区間: ${total}`));

  document.querySelectorAll('[data-indicator]').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.indicator === state.indicator)));
}

/** 区間の表示名から幅員の注記を外す: 「国道（幅員3〜5.5m）」→「国道」 */
export function withoutWidth(text) {
  return (text || '').replace(/（幅員[^）]*）/g, '');
}

// ---- 注意区間一覧 ---------------------------------------------------------
export function renderAlertList(onPick) {
  const ind = INDICATORS[state.indicator];
  el('alertListTitle').textContent = ind.alertLabel;
  const items = [];
  for (const [id, rep] of Object.entries(state.status?.segments || {})) {
    const key = ind.classify(rep);
    if (!ind.isAlert(key) || state.filters[key] === false) continue;
    items.push({ id: Number(id), rep, cls: classInfo(state.indicator, key) });
  }
  const props = (id) => getLayer(id)?.feature.properties || {};
  const groups = groupAlerts(items, {
    routeOf: (id) => withoutWidth(props(id).label),
    muniOf: (id) => props(id).muni,
    lengthOf,
  });
  el('alertCount').textContent = groups.length ? `${groups.length} 件` : '';
  const list = el('alertList');
  if (!groups.length) {
    list.replaceChildren(h('li', { class: 'empty' }, '表示範囲内に該当する区間はありません'));
    return;
  }
  const MAX = 50;
  list.replaceChildren(...groups.slice(0, MAX).map((g) => {
    const { rep, cls } = g.worst;
    const multi = g.ids.length > 1;
    // 主: どこで（路線・市町村）/ 従: 状態と範囲
    const place = [g.route, g.muni].filter(Boolean).join(' ');
    const status = state.indicator === 'wips'
      ? `${cls.label.split('：')[1]}（WIPS ${multi ? '最低 ' : ''}${rep.wips.toFixed(2)}）`
      : g.classes.map((c) => c.label).join('・');
    const extent = multi ? `${g.ids.length}区間・計 ${lengthLabel(g.length)}` : lengthLabel(g.length);
    return h('li', {},
      h('button', { type: 'button', class: 'alert-item', onclick: () => onPick(g) },
        h('span', { class: 'sw', style: `--c:${cls.color}` }),
        h('span', { class: 'alert-main' },
          h('span', { class: 'alert-place' }, place || '路線名不明'),
          h('span', { class: 'alert-sub' }, status),
          h('span', { class: 'alert-sub' }, extent)),
        h('span', { class: 'alert-time' }, time.short(time.parse(g.latest)),
          h('small', {}, time.ageLabel(g.ageMinutes))),
      ));
  }));
  if (groups.length > MAX) list.append(h('li', { class: 'empty' }, `ほか ${groups.length - MAX} 件`));
  if (items.length > groups.length) {
    list.append(h('li', { class: 'empty' }, `${items.length} 区間を路線・市町村ごとに ${groups.length} 件にまとめています`));
  }
}

// ---- 詳細 -----------------------------------------------------------------
export function renderDetail(segId, rep, { onImage }) {
  const panel = el('detailPanel');
  const props = getLayer(segId)?.feature.properties || {};
  const name = withoutWidth(props.label);
  const kind = withoutWidth(props.kind);
  el('detailTitle').textContent = name || '選択区間';
  // 路線名が分かった区間は「市町村 ・ 道路分類」、分からない区間は市町村だけを添える
  el('detailSub').textContent = [props.muni, name !== kind ? kind : ''].filter(Boolean).join(' ・ ');
  const body = el('detailBody');
  panel.hidden = false;

  if (!rep) {
    body.replaceChildren(
      h('p', {}, '表示期間内にこの区間の観測はありません。'),
      h('p', { class: 'muted' }, '時間スライダーの範囲を広げるか、過去データを検索してください。'),
    );
    return;
  }

  const wCls = classInfo('wips', INDICATORS.wips.classify(rep));
  const sCls = classInfo('surface', INDICATORS.surface.classify(rep));
  const isLive = state.mode === 'live';

  const img = rep.image_url
    ? h('button', { type: 'button', class: 'thumb', 'aria-label': '画像を拡大', onclick: () => onImage(rep) },
        h('img', { src: rep.image_url, alt: `${rep.observed_at} の路面画像`, loading: 'lazy',
          onerror: (e) => e.target.closest('.thumb').replaceWith(h('p', { class: 'no-image' }, '画像を読み込めませんでした')) }))
    : h('p', { class: 'no-image' }, 'この観測の画像はありません');

  body.replaceChildren(
    h('div', { class: 'kpis' },
      h('div', { class: 'kpi', style: `--c:${wCls.color}` },
        h('span', { class: 'kpi-label' }, '視界 WIPS'),
        h('span', { class: 'kpi-value' }, rep.wips != null ? rep.wips.toFixed(2) : '—'),
        h('span', { class: 'kpi-tag' }, rep.wips != null ? wCls.label.split('：')[1] : '欠損')),
      h('div', { class: 'kpi', style: `--c:${sCls.color}` },
        h('span', { class: 'kpi-label' }, '路面状態'),
        h('span', { class: 'kpi-value kpi-text' }, surfaceLabel(rep.road_surface)),
        h('span', { class: 'kpi-tag' }, rep.road_surface || '')),
    ),
    h('dl', { class: 'facts' },
      h('dt', {}, '観測時刻'),
      h('dd', {}, time.short(time.parse(rep.observed_at)), ' ',
        h('span', { class: 'muted' }, isLive ? `（${time.ageLabel(rep.age_minutes)}）`
          : `（表示範囲の終わりの${time.ageLabel(rep.age_minutes)}）`)),
    ),
    img,
  );
}

export function hideDetail() {
  el('detailPanel').hidden = true;
}
