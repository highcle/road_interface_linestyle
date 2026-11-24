// 時刻ユーティリティ
// サーバーとは "YYYY-MM-DD HH:MM:SS"（日本時間・タイムゾーンなし）でやり取りする。
// ブラウザのタイムゾーンに左右されないよう、内部では「その壁時計時刻を UTC とみなした」
// ミリ秒値で扱い、表示も getUTC* で行う。

export function parse(str) {
  if (!str) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(str);
  if (!m) return null;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
}

const p2 = (n) => String(n).padStart(2, '0');

export function format(ms) {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())} ` +
         `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:${p2(d.getUTCSeconds())}`;
}

/** datetime-local 入力用 "YYYY-MM-DDTHH:MM" */
export function toInput(ms) {
  return format(ms).slice(0, 16).replace(' ', 'T');
}

export function short(ms, { withDate = true } = {}) {
  const d = new Date(ms);
  const hm = `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
  return withDate ? `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${hm}` : hm;
}

export function sameDay(a, b) {
  return format(a).slice(0, 10) === format(b).slice(0, 10);
}

export function rangeLabel(startMs, endMs) {
  return `${short(startMs)} 〜 ${sameDay(startMs, endMs) ? short(endMs, { withDate: false }) : short(endMs)}`;
}

export function ageLabel(minutes) {
  if (minutes == null) return '';
  if (minutes < 1) return 'たった今';
  if (minutes < 60) return `${minutes}分前`;
  const h = Math.floor(minutes / 60);
  if (h < 24) return `${h}時間${minutes % 60 ? `${minutes % 60}分` : ''}前`;
  return `${Math.floor(h / 24)}日${h % 24 ? `${h % 24}時間` : ''}前`;
}

export function durationLabel(ms) {
  const min = Math.round(ms / 60000);
  if (min < 60) return `${min}分間`;
  const h = Math.floor(min / 60), m = min % 60;
  if (h < 48) return `${h}時間${m ? `${m}分` : ''}`;
  return `${Math.floor(h / 24)}日${h % 24 ? `${h % 24}時間` : ''}`;
}

export const MIN = 60 * 1000;
export const HOUR = 60 * MIN;
export const DAY = 24 * HOUR;
