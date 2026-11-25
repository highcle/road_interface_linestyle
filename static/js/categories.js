// 指標の区分と配色
// 配色は「青=安全 → 黄/橙=注意 → 赤=危険」の順序を、WIPS と路面状態で共通にしている。

const T = window.APP_CONFIG.thresholds;

export const COLORS = {
  none: '#9aa3ad',
};

export const INDICATORS = {
  wips: {
    label: '視界（WIPS）',
    alertLabel: '視程不良・注意の区間',
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
    alertLabel: '凍結・積雪・シャーベットの区間',
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

// ---- 連続色（グラデーション用） ------------------------------------------------
// 区分の色を危険度レベル順に並べ、レベルの小数値を OKLCh 色空間で補間する。
// RGB で補間すると青→黄の途中が灰色にくすむため、色相を回して（青→青緑→緑→黄→赤）つなぐ。
function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const toLin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const fromLin = (c) => {
  const v = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
  return Math.round(Math.min(1, Math.max(0, v)) * 255);
};
function rgbToOklch([r, g, b]) {
  [r, g, b] = [toLin(r), toLin(g), toLin(b)];
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
  return [L, Math.hypot(A, B), Math.atan2(B, A)];
}
function oklchToHex([L, C, h]) {
  const A = C * Math.cos(h), B = C * Math.sin(h);
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ].map(fromLin);
  return `#${rgb.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}
const rampCache = {};
function ramp(indicator) {
  if (!rampCache[indicator]) {
    rampCache[indicator] = INDICATORS[indicator].classes
      .filter((c) => c.level >= 0).sort((a, b) => a.level - b.level)
      .map((c) => rgbToOklch(hexToRgb(c.color)));
  }
  return rampCache[indicator];
}

/** 危険度レベル（小数可）の色。整数レベルでは区分の色そのもの */
export function levelColor(indicator, level) {
  const r = ramp(indicator);
  const x = Math.min(r.length - 1, Math.max(0, level));
  const i = Math.min(r.length - 2, Math.floor(x));
  const t = x - i;
  const [L0, C0, h0] = r[i], [L1, C1, h1] = r[i + 1];
  let dh = h1 - h0;
  if (dh > Math.PI) dh -= 2 * Math.PI;
  if (dh < -Math.PI) dh += 2 * Math.PI;   // 色相は近い向きに回す
  return oklchToHex([L0 + (L1 - L0) * t, C0 + (C1 - C0) * t, h0 + dh * t]);
}
