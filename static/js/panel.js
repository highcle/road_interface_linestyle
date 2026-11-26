// 右パネル: 凡例/フィルタ、注意区間一覧、選択区間の詳細
import { state, savePrefs } from './state.js';
import { INDICATORS, COLORS, WIPS_SCALE, classInfo, surfaceLabel, wipsColor, bandCss } from './categories.js';
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
  const shaded = state.gradient && state.indicator === 'wips';
  const make = (key, label, color, count, thin) => h('label', { class: 'legend-item' },
    h('input', {
      type: 'checkbox', checked: state.filters[key] !== false,
      onchange: (e) => { state.filters[key] = e.target.checked; savePrefs(); onFilterChange(); },
    }),
    h('span', { class: `sw${thin ? ' sw-thin' : ''}`,
      style: `--c:${(shaded && bandCss(key)) || color}` }),
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
  el('legendArea').replaceChildren(order, list, shaded ? colorBar() : null,
    h('p', { class: 'legend-total' }, `観測のある区間: ${total}`));

  document.querySelectorAll('[data-indicator]').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.indicator === state.indicator)));
}

/** WIPS の濃淡のカラーバー（左=視界が悪い、右=良い）。区分の境界で色が切り替わる */
function colorBar() {
  let pos = 0;
  const stops = [];
  const ticks = [];
  for (const b of WIPS_SCALE) {
    stops.push(`${b.from} ${pos}%`, `${b.to} ${pos + b.width}%`);
    if (pos > 0) ticks.push(h('span', { class: 'cb-tick', style: `left:${pos}%` }, b.min.toFixed(1)));
    pos += b.width;
  }
  const first = WIPS_SCALE[0], last = WIPS_SCALE[WIPS_SCALE.length - 1];
  return h('div', { class: 'colorbar', role: 'img',
    'aria-label': `WIPS の値と色: ${first.min.toFixed(1)} 以下から ${last.max.toFixed(1)} 以上まで` },
    h('p', { class: 'cb-title' }, '線の色の濃さ＝その区間の WIPS 実測値'),
    h('div', { class: 'cb-bar', style: `background: linear-gradient(90deg, ${stops.join(', ')})` }),
    h('div', { class: 'cb-ticks' },
      h('span', { class: 'cb-tick cb-first', style: 'left:0' }, `${first.min.toFixed(1)}以下`),
      ticks,
      h('span', { class: 'cb-tick cb-last', style: 'left:100%' }, `${last.max.toFixed(1)}以上`)),
  );
}

/** 地図の線と同じ色（WIPS の濃淡表示中は実測値の色） */
function lineColor(rep, cls) {
  return state.gradient && state.indicator === 'wips' && rep.wips != null ? wipsColor(rep.wips) : cls.color;
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
    routeOf: (id) => props(id).label,
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
    const value = state.indicator === 'wips'
      ? `${multi ? '最も悪い区間 ' : ''}WIPS ${rep.wips.toFixed(2)}`
      : g.classes.map((c) => c.label).join('・');
    const place = [g.route, g.muni].filter(Boolean).join(' ・ ');
    const extent = multi ? `${g.ids.length}区間・計 ${lengthLabel(g.length)}` : lengthLabel(g.length);
    return h('li', {},
      h('button', { type: 'button', class: 'alert-item', onclick: () => onPick(g) },
        h('span', { class: 'sw', style: `--c:${lineColor(rep, cls)}` }),
        h('span', { class: 'alert-main' },
          h('span', { class: 'alert-value' }, value),
          h('span', { class: 'alert-sub' }, place),
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

/** 一覧用の短い表記: 「国道5号 ・ 小樽市」 */
function placeLabel(props) {
  if (!props) return '';
  return [props.label, props.muni].filter(Boolean).join(' ・ ');
}

// ---- 詳細 -----------------------------------------------------------------
export function renderDetail(segId, rep, { onImage, timelinePromise }) {
  const panel = el('detailPanel');
  const props = getLayer(segId)?.feature.properties || {};
  el('detailTitle').textContent = props.label || '選択区間';
  // 路線名が分かった区間は「市町村 ・ 道路分類（幅員）」、分からない区間は市町村だけを添える
  el('detailSub').textContent = [props.muni, props.label !== props.kind ? props.kind : '']
    .filter(Boolean).join(' ・ ');
  const body = el('detailBody');
  panel.hidden = false;

  if (!rep) {
    body.replaceChildren(
      h('p', { class: 'muted' }, `区間ID ${segId}`),
      h('p', {}, '表示期間内にこの区間の観測はありません。'),
      h('p', { class: 'muted' }, '時間スライダーの範囲を広げるか、過去データを検索してください。'),
    );
    return;
  }

  const wKey = INDICATORS.wips.classify(rep);
  const sKey = INDICATORS.surface.classify(rep);
  const wCls = classInfo('wips', wKey);
  const sCls = classInfo('surface', sKey);
  const s = rep.stats;
  const obsAt = time.parse(rep.observed_at);
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
      h('dd', {}, time.short(obsAt), ' ',
        h('span', { class: 'muted' }, isLive ? `（${time.ageLabel(rep.age_minutes)}）`
          : `（表示範囲の終わりの${time.ageLabel(rep.age_minutes)}）`)),
      h('dt', {}, '代表点'),
      h('dd', {}, `最新の通過（${time.rangeLabel(time.parse(rep.pass.start), time.parse(rep.pass.end))}、${rep.pass.n_obs}観測）`,
        state.status?.algorithm?.id === 'latest_pass_min_wips' ? 'のうち WIPS 最小の観測'
          : `の WIPS 中央値${rep.pass.wips_median != null ? `（${rep.pass.wips_median.toFixed(2)}）` : ''}に最も近い観測`),
      // 色の判定には使わない参考情報: 代表点より前に、もっと悪い値が出ていなかったか
      h('dt', {}, `この${time.durationLabel(state.range.end - state.range.start)}`),
      h('dd', {}, `${s.n_obs}回観測（${s.n_passes}回通過）`,
        s.wips_min != null ? h('span', { class: 'muted' },
          `、WIPS 最低 ${s.wips_min.toFixed(2)}・最高 ${s.wips_max.toFixed(2)}`) : null),
    ),
    h('div', { class: 'timeline', id: 'timelineChart' }, h('p', { class: 'muted' }, '推移を読み込み中…')),
    img,
    h('p', { class: 'muted seg-id' }, `区間ID ${segId}`),
  );

  // 応答が届くまでに別の区間を選んだ・再描画した場合は描かない
  const box = document.getElementById('timelineChart');
  const stillShown = () => box.isConnected && state.selectedId === segId;
  timelinePromise
    .then((obs) => { if (stillShown()) box.replaceChildren(sparkline(obs, rep)); })
    .catch(() => { if (stillShown()) box.replaceChildren(h('p', { class: 'muted' }, '推移を取得できませんでした')); });
}

export function hideDetail() {
  el('detailPanel').hidden = true;
}

/** 表示範囲内の WIPS 推移（点=観測、色=路面状態、◇=代表点） */
function sparkline(obs, rep) {
  const NS = 'http://www.w3.org/2000/svg';
  const W = 280, H = 110, PL = 30, PR = 6, PT = 8, PB = 18;
  const s = (tag, attrs, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };
  const pts = obs.filter((o) => o.wips != null);
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, class: 'spark', role: 'img',
    'aria-label': `WIPS の推移（${pts.length} 観測）` });
  if (!pts.length) {
    svg.append(s('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'spark-empty' }, '有効な WIPS がありません'));
    return svg;
  }
  const t0 = state.range.start, t1 = state.range.end;
  const vals = pts.map((o) => o.wips);
  const yMin = Math.min(T.danger - 1, ...vals) - 0.3, yMax = Math.max(T.warn + 1, ...vals) + 0.3;
  const x = (t) => PL + ((t - t0) / Math.max(1, t1 - t0)) * (W - PL - PR);
  const y = (v) => PT + (1 - (v - yMin) / (yMax - yMin)) * (H - PT - PB);

  // 閾値の帯
  svg.append(s('rect', { x: PL, y: y(T.danger), width: W - PL - PR, height: Math.max(0, y(yMin) - y(T.danger)), class: 'band-danger' }));
  svg.append(s('rect', { x: PL, y: y(T.warn), width: W - PL - PR, height: Math.max(0, y(T.danger) - y(T.warn)), class: 'band-warn' }));
  for (const v of [T.danger, T.warn]) {
    svg.append(s('line', { x1: PL, x2: W - PR, y1: y(v), y2: y(v), class: 'th-line' }));
  }
  // 閾値ラベル（近すぎて重なる場合は外側にずらす）
  const ld = y(T.danger), lw = Math.min(y(T.warn), ld - 9);
  svg.append(s('text', { x: PL - 4, y: ld + 6, 'text-anchor': 'end', class: 'axis' }, T.danger.toFixed(1)));
  svg.append(s('text', { x: PL - 4, y: lw, 'text-anchor': 'end', class: 'axis' }, T.warn.toFixed(1)));
  svg.append(s('text', { x: PL, y: H - 4, class: 'axis' }, time.short(t0)));
  svg.append(s('text', { x: W - PR, y: H - 4, 'text-anchor': 'end', class: 'axis' }, time.short(t1)));

  for (const o of pts) {
    const t = time.parse(o.t);
    const c = classInfo('surface', INDICATORS.surface.classify(o)).color;
    const dot = s('circle', { cx: x(t), cy: y(o.wips), r: 2.8, fill: c, class: 'dot' });
    dot.append(s('title', {}, `${time.short(t)}  WIPS ${o.wips.toFixed(2)} / ${surfaceLabel(o.road_surface)} / ${o.pass_no}回目の通過`));
    svg.append(dot);
  }
  const rt = time.parse(rep.observed_at);
  if (rep.wips != null) {
    const cx = x(rt), cy = y(rep.wips);
    const mark = s('path', { d: `M${cx} ${cy - 6} L${cx + 6} ${cy} L${cx} ${cy + 6} L${cx - 6} ${cy} Z`, class: 'rep-mark' });
    mark.append(s('title', {}, `代表点 ${time.short(rt)} WIPS ${rep.wips.toFixed(2)}`));
    svg.append(mark);
  }
  return svg;
}
