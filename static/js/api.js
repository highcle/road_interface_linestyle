// サーバー API 呼び出し
import * as time from './time.js';

const ROOT = window.APP_CONFIG.root || '';

export class ApiError extends Error {}

async function getJson(path, params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null) qs.set(k, v);
  const url = `${ROOT}${path}${qs.toString() ? `?${qs}` : ''}`;
  let res;
  try {
    res = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch {
    throw new ApiError('サーバーに接続できません。ネットワークを確認してください。');
  }
  let body = null;
  try { body = await res.json(); } catch { /* 下で処理 */ }
  if (!res.ok) throw new ApiError(body?.error || `サーバーエラー（${res.status}）`);
  if (body == null) throw new ApiError('サーバーの応答を読み取れませんでした。');
  return body;
}

function rangeParams({ history, range }) {
  return {
    base_start: history ? time.format(history.start) : null,
    base_end: history ? time.format(history.end) : null,
    start: range ? time.format(range.start) : null,
    end: range ? time.format(range.end) : null,
  };
}

export const fetchGeometry = () =>
  getJson('/api/roads/geometry', { v: window.APP_CONFIG.geometryVersion });

export const fetchStatus = (opts) => getJson('/api/roads/status', rangeParams(opts));

export const fetchTimeline = (segId, opts) => getJson(`/api/roads/${segId}/timeline`, rangeParams(opts));

/** 国土地理院 住所検索 API */
export async function geocode(q) {
  const res = await fetch(`https://msearch.gsi.go.jp/address-search/AddressSearch?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new ApiError('地名検索に失敗しました');
  return res.json();
}
