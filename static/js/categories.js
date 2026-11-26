// 指標の区分と配色
// 配色は「青=安全 → 黄/橙=注意 → 赤=危険」の順序を、WIPS と路面状態で共通にしている。

const T = window.APP_CONFIG.thresholds;

export const COLORS = {
  none: '#9aa3ad',
};

export const INDICATORS = {
  wips: {
    label: '視界（WIPS）',
    alertLabel: '視程不良・注意の区間（路線・市町村別）',
    classes: [
      { key: 'wips_good', label: `${T.warn.toFixed(1)} 以上：良好`, color: '#1f6fb2', level: 0 },
      { key: 'wips_warn', label: `${T.danger.toFixed(1)} 超〜${T.warn.toFixed(1)} 未満：注意`, color: '#e3a100', level: 1 },
      { key: 'wips_danger', label: `${T.danger.toFixed(1)} 以下：視程不良`, color: '#c4162a', level: 2 },
      { key: 'wips_none', label: 'WIPS 欠損（異常値など）', color: COLORS.none, level: -1, dataless: true },
    ],
    classify(rep) {
      if (rep.wips == null) return 'wips_none';
      if (rep.wips <= T.danger) return 'wips_danger';
      if (rep.wips < T.warn) return 'wips_warn';
      return 'wips_good';
    },
    isAlert: (key) => key === 'wips_danger' || key === 'wips_warn',
  },
  surface: {
    label: '路面状態',
    alertLabel: '凍結・積雪・シャーベットの区間（路線・市町村別）',
    // 滑りやすさの目安順
    classes: [
      { key: 'dry', label: '乾燥', color: '#1f6fb2', level: 0 },
      { key: 'semi-wet', label: '半湿潤', color: '#2a9d8f', level: 1 },
      { key: 'wet', label: '湿潤', color: '#7cb342', level: 2 },
      { key: 'slush', label: 'シャーベット', color: '#e3a100', level: 3 },
      { key: 'fresh', label: '積雪（新雪）', color: '#ec6b1e', level: 4 },
      { key: 'ice', label: '凍結', color: '#c4162a', level: 5 },
      { key: 'surface_other', label: 'その他・不明', color: '#6d5c8f', level: -1, dataless: true },
    ],
    classify(rep) {
      const s = (rep.road_surface || '').toLowerCase();
      if (['dry', 'semi-wet', 'wet', 'slush', 'fresh', 'ice'].includes(s)) return s;
      return 'surface_other';
    },
    isAlert: (key) => key === 'ice' || key === 'fresh' || key === 'slush',
  },
};

export function classInfo(indicator, key) {
  return INDICATORS[indicator].classes.find((c) => c.key === key);
}

export function surfaceLabel(value) {
  const c = classInfo('surface', INDICATORS.surface.classify({ road_surface: value }));
  return value ? (c.key === 'surface_other' ? value : c.label) : 'データなし';
}

/** 観測からの経過時間に応じた不透明度（古いほど薄い） */
export function freshnessOpacity(ageMinutes) {
  if (ageMinutes == null) return 0.9;
  if (ageMinutes <= 60) return 0.95;
  if (ageMinutes <= 180) return 0.8;
  if (ageMinutes <= 360) return 0.62;
  return 0.45;
}

// ---- WIPS の値による濃淡 -------------------------------------------------------
// 区間の色を、その区間で実測した WIPS の値そのものから決める（隣の区間と混ぜない）。
// 区分ごとに同系色の範囲だけを使い、区分の境界（7.5・8.0）では色を切り替える。
// 色はすべて凡例のカラーバー上にあり、カラーバー上の位置＝実測値になる。
export const WIPS_SCALE = [
  // 視程不良: 暗い赤（低い）→ 赤（境界）
  { key: 'wips_danger', min: 4.0, max: T.danger, from: '#5c0011', to: '#d42a1c', width: 40 },
  // 注意: 橙 → 黄
  { key: 'wips_warn', min: T.danger, max: T.warn, from: '#ec7014', to: '#f2b600', width: 20 },
  // 良好: 明るい青（境界）→ 濃い紺（高い）
  { key: 'wips_good', min: T.warn, max: 10.0, from: '#7fb6dd', to: '#0b2f6b', width: 40 },
];

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function mix(a, b, t) {
  const [x, y] = [hexToRgb(a), hexToRgb(b)];
  return `#${x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('')}`;
}

/** WIPS の実測値の色。値が範囲外なら端の色。区分は INDICATORS.wips.classify と同じ基準 */
export function wipsColor(wips) {
  const key = INDICATORS.wips.classify({ wips });
  const band = WIPS_SCALE.find((b) => b.key === key);
  if (!band) return COLORS.none;
  const t = Math.min(1, Math.max(0, (wips - band.min) / (band.max - band.min)));
  return mix(band.from, band.to, t);
}

/** 区分の濃淡を表す CSS グラデーション（凡例の見本用） */
export function bandCss(key) {
  const b = WIPS_SCALE.find((x) => x.key === key);
  return b ? `linear-gradient(90deg, ${b.from}, ${b.to})` : null;
}
