// 注意区間を「路線 × 市町村」ごとにまとめる
// 道路データは短い区間（中央値 約84m）に分かれているため、1回の通過で視程が悪かった道が
// 数十区間として並んでしまう。端点のつながりでまとめても、悪い値と良い値の区間が交互に
// 並ぶため細切れのまま残る（テストDBの6時間で 364区間 → 200か所）。
// そこで道路管理で使う単位の「路線 × 市町村」で1件にまとめる（同 364区間 → 42件）。
// 値は各区間の代表点そのもので、まとめた件では最も悪い区間の値を示す（新しい値は作らない）。

/**
 * 路線のまとめ用キー。重複区間（「国道40号・239号」）は先頭の国道（国道40号）にまとめる。
 * 路線名が分からない区間は道路分類の表記（label）のまま。
 */
export function routeKey(label) {
  const m = /^国道(\d+)号/.exec(label || '');
  return m ? `国道${m[1]}号` : (label || '');
}

/**
 * @param {Array<{id:number, rep:object, cls:object}>} items 注意区間
 * @param {{routeOf:(id)=>string, muniOf:(id)=>string, lengthOf:(id)=>number}} geo
 * @returns {Array<{ids:number[], worst:object, latest:string, ageMinutes:number, route:string, muni:string, length:number, classes:object[]}>}
 */
export function groupAlerts(items, geo) {
  const byKey = new Map();
  for (const it of items) {
    const route = routeKey(geo.routeOf(it.id));
    const muni = geo.muniOf(it.id) || '';
    const key = `${route}\u0000${muni}`;
    if (!byKey.has(key)) byKey.set(key, { route, muni, members: [] });
    byKey.get(key).members.push(it);
  }
  const groups = [...byKey.values()].map(({ route, muni, members }) => summarize(members, route, muni, geo));
  // 危険度の高い順 → 値の悪い順 → 長い順 → 新しい順
  groups.sort((a, b) => b.worst.cls.level - a.worst.cls.level
    || (a.worst.rep.wips ?? Infinity) - (b.worst.rep.wips ?? Infinity)
    || b.length - a.length
    || b.latest.localeCompare(a.latest));
  return groups;
}

/** 最も悪い区間: 危険度が高い → WIPS が低い → 新しい */
function worse(a, b) {
  return b.cls.level - a.cls.level
    || (a.rep.wips ?? Infinity) - (b.rep.wips ?? Infinity)
    || b.rep.observed_at.localeCompare(a.rep.observed_at);
}

function summarize(members, route, muni, geo) {
  const sorted = [...members].sort(worse);
  const classes = [];
  for (const m of sorted) if (!classes.includes(m.cls)) classes.push(m.cls);
  return {
    ids: members.map((m) => m.id),
    worst: sorted[0],
    latest: members.reduce((t, m) => (m.rep.observed_at > t ? m.rep.observed_at : t), ''),
    ageMinutes: Math.min(...members.map((m) => m.rep.age_minutes)),
    route,
    muni,
    length: members.reduce((s, m) => s + geo.lengthOf(m.id), 0),
    classes,
  };
}

/** 「約 340 m」「約 1.2 km」 */
export function lengthLabel(m) {
  if (m < 1000) return `約 ${Math.max(10, Math.round(m / 10) * 10)} m`;
  return `約 ${(m / 1000).toFixed(m < 10000 ? 1 : 0)} km`;
}
