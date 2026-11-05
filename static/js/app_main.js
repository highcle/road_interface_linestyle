// 地図の初期化
AppState.map = L.map('map');
L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>'
}).addTo(AppState.map);

// 地図の移動・ズーム時に矢印線を自動更新
AppState.map.on('move zoom', updateConnectorLine);
AppState.map.on('click', clearSelection);

// レイヤースタイルの一括更新
function refreshLayerStyles() {
  if (!AppState.geojsonLayer) return;
  const range = getSliderTimeRange();
  AppState.geojsonLayer.setStyle(feat => getFeatureStyle(feat, range.startStr, range.endStr));
}

// 1. 直近24時間データの取得 (5分ごとの自動更新時にも使用)
function fetchRecentData(isAutoUpdate = false) {
  const statusEl = document.getElementById('status');
  
  // 自動更新以外（初回読み込み時など）の場合のみローディング表示
  if (!isAutoUpdate) {
    document.getElementById('loadingOverlay').style.display = 'flex';
  }

  fetch('/api/roads/recent')
    .then(res => res.json())
    .then(data => {
      document.getElementById('loadingOverlay').style.display = 'none';
      AppState.raw24hData = data;

      if (AppState.geojsonLayer) {
        AppState.geojsonLayer.clearLayers();
        AppState.geojsonLayer.addData(data);
      } else {
        AppState.geojsonLayer = L.geoJSON(data, {
          style: (feat) => {
            const range = getSliderTimeRange();
            return getFeatureStyle(feat, range.startStr, range.endStr);
          },
          onEachFeature: (feature, layer) => {
            layer.on('click', (e) => {
              L.DomEvent.stopPropagation(e);
              // セグメントの中央座標を取得（取得できない場合はクリック座標を使用）
              const centerLatLng = (layer.getBounds && typeof layer.getBounds === 'function')
                ? layer.getBounds().getCenter()
                : e.latlng;
              selectRoadSegment(feature, centerLatLng);
            });
          }
        }).addTo(AppState.map);
      }

      if (AppState.isFirstLoad) {
        const bounds = AppState.geojsonLayer.getBounds();
        if (bounds.isValid()) AppState.map.fitBounds(bounds, { padding: [40, 40] });
        AppState.isFirstLoad = false;
      }

      refreshLayerStyles();
      updateLegend();
      updateConnectorLine();
      statusEl.innerText = `最終更新: ${new Date().toLocaleTimeString()}`;
    })
    .catch(err => {
      document.getElementById('loadingOverlay').style.display = 'none';
      console.error(err);
      statusEl.innerText = "更新エラー";
    });
}

// 2. 過去指定データの取得（手動検索）
function fetchHistoryRoadData(startStr, endStr) {
  const statusEl = document.getElementById('status');
  document.getElementById('loadingOverlay').style.display = 'flex';

  fetch(`/api/roads/search?start_time=${encodeURIComponent(startStr)}&end_time=${encodeURIComponent(endStr)}`)
    .then(res => res.json())
    .then(data => {
      document.getElementById('loadingOverlay').style.display = 'none';
      
      if (AppState.geojsonLayer) {
        AppState.geojsonLayer.clearLayers();
        AppState.geojsonLayer.addData(data);
      } else {
        AppState.geojsonLayer = L.geoJSON(data, {
          style: (feat) => getFeatureStyle(feat, startStr, endStr),
          onEachFeature: (feature, layer) => {
            layer.on('click', (e) => {
              L.DomEvent.stopPropagation(e);
              const centerLatLng = (layer.getBounds && typeof layer.getBounds === 'function')
                ? layer.getBounds().getCenter()
                : e.latlng;
              selectRoadSegment(feature, centerLatLng);
            });
          }
        }).addTo(AppState.map);
      }

      refreshLayerStyles();
      updateLegend();
      updateConnectorLine();
      statusEl.innerText = `過去検索完了: ${new Date().toLocaleTimeString()}`;
    })
    .catch(err => {
      document.getElementById('loadingOverlay').style.display = 'none';
      console.error(err);
      statusEl.innerText = "検索エラー";
    });
}

// セグメント選択
function selectRoadSegment(feature, latlng) {
  AppState.selectedFeature = feature;
  AppState.selectedLatLng = latlng;

  const p = feature.properties;
  const detailPanel = document.getElementById('detailPanel');
  const detailInfo = document.getElementById('detailInfo');
  const imgContainer = document.getElementById('imagePreviewContainer');

  detailInfo.innerHTML = `
    <b>路線名:</b> ${p.display_route_name || '対象路線'}<br/>
    <b>WIPS値:</b> <b>${p.wips !== null ? p.wips : 'データなし'}</b><br/>
    <b>路面状態:</b> <b>${p.road_surface || 'データなし'}</b><br/>
    <b>最終更新:</b> ${p.last_updated || '-'}<br/>
    <b>画像名:</b> ${p.image_path || '-'}
  `;

  if (p.image_path) {
    const imgUrl = `/static/images/_indicated_bus_${p.image_path.slice(26, -4)}/${p.image_path.slice(6, 12)}/${p.image_path}`;
    
    imgContainer.innerHTML = `<img src="${imgUrl}" alt="路面画像" onerror="this.onerror=null; this.parentNode.innerHTML='<div class=\\'no-image\\'>画像が読み込めませんでした</div>';"/>`;
    
    //imgContainer.innerHTML = `<img src="/images/${p.image_path}" alt="路面画像" onerror="this.onerror=null; this.parentNode.innerHTML='<div class=\\'no-image\\'>画像が読み込めませんでした</div>';"/>`;
  } else {
    imgContainer.innerHTML = `<div class="no-image">この区間の画像はありません</div>`;
  }

  detailPanel.style.display = 'block';
  
  // 接続矢印線の描画更新
  updateConnectorLine();
}

function clearSelection() {
  AppState.selectedFeature = null;
  AppState.selectedLatLng = null;
  document.getElementById('detailPanel').style.display = 'none';
  clearConnectorLine();
}

// 5分間隔 (300,000 ms) の自動更新（ローディング表示なし）
setInterval(() => {
  const autoUpdateChecked = document.getElementById('autoUpdate').checked;
  if (autoUpdateChecked && !AppState.customSearchMode) {
    fetchRecentData(true);
  }
}, 300000);

// 初回読み込み
fetchRecentData(false);