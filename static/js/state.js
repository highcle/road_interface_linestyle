// 全体共通状態オブジェクト
const AppState = {
  map: null,
  geojsonLayer: null,
  raw24hData: null,         // ★ キャッシュされた直近24時間の全GeoJSON
  selectedFeature: null,    // 選択されたセグメント
  selectedLatLng: null,     // 選択されたセグメントの中心座標
  isFirstLoad: true,
  customSearchMode: false,  // 過去データモーダル検索中か
  
  // フィルタ状態
  visibleFilters: {
    wips_good: true, wips_warn: true, wips_danger: true, wips_none: true,
    dry: true, wet: true, semi_wet: true, fresh: true, slush: true, ice: true, other: true, surface_none: true
  }
};