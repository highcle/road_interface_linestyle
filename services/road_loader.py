"""道路ネットワーク（国土数値情報 N13）の読み込み。

GeoJSON 全体（約270MB）の解析に数秒かかるため、対象道路だけを抽出した結果を
cache/ に pickle で保存し、元ファイルが変わらない限り再利用する。
"""
import glob
import hashlib
import json
import logging
import os
import pickle

import geopandas as gpd

import config

log = logging.getLogger(__name__)

CACHE_VERSION = 2


def _source_files(geojson_dir):
    files = set()
    for ext in ("*.geojson", "*.json"):
        files.update(glob.glob(os.path.join(geojson_dir, "**", ext), recursive=True))
    return sorted(files)


def roads_signature(geojson_dir=config.GEOJSON_DIR, target_types=config.TARGET_ROAD_TYPES):
    """元データと抽出条件から決まる識別子。道路IDの整合性チェックに使う。"""
    h = hashlib.sha1(f"v{CACHE_VERSION}|{sorted(target_types)}".encode())
    for f in _source_files(geojson_dir):
        st = os.stat(f)
        h.update(f"{os.path.basename(f)}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()[:12]


def road_label(props):
    """路線名の代わりに表示する区間ラベル。

    N13 には路線名・路線番号の属性が無いため、道路分類と幅員区分から組み立てる。
    """
    cls = config.ROAD_CLASS_LABELS.get(str(props.get("N13_003")), "道路")
    width = config.ROAD_WIDTH_LABELS.get(str(props.get("N13_006")))
    return f"{cls}（{width}）" if width else cls


def _load_from_geojson(geojson_dir, target_types):
    features = []
    for fpath in _source_files(geojson_dir):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            log.warning("道路データを読み込めませんでした: %s (%s)", fpath, e)
            continue
        items = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
        for item in items:
            props = item.get("properties") or {}
            if str(props.get("N13_003")) in target_types:
                features.append({
                    "type": "Feature",
                    "geometry": item.get("geometry"),
                    "properties": {
                        "road_class": str(props.get("N13_003")),
                        "width_class": str(props.get("N13_006")),
                        "label": road_label(props),
                    },
                })
    if not features:
        raise RuntimeError(f"対象道路が見つかりません: {geojson_dir}（geojson.tar.xz を展開しましたか？）")

    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:6668")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)
    gdf.index.name = "seg_id"
    return gdf


def load_roads(geojson_dir=config.GEOJSON_DIR, target_types=config.TARGET_ROAD_TYPES,
               cache_dir=config.CACHE_DIR):
    """対象道路を読み込む。戻り値の index (seg_id) が区間IDになる。

    Returns:
        (gdf_roads, signature)  gdf_roads は EPSG:6668 (JGD2011 経緯度)
    """
    sig = roads_signature(geojson_dir, target_types)
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"roads_{sig}.pkl")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            gdf = pickle.load(f)
        log.info("道路データをキャッシュから読み込みました (%d 区間)", len(gdf))
        return gdf, sig

    log.info("道路データを GeoJSON から読み込みます: %s", geojson_dir)
    gdf = _load_from_geojson(geojson_dir, target_types)
    tmp = cache_path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(gdf, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, cache_path)
    # 古い署名のキャッシュを掃除
    for old in glob.glob(os.path.join(cache_dir, "roads_*.pkl")):
        if old != cache_path:
            os.remove(old)
    log.info("道路データ %d 区間を読み込み、キャッシュしました", len(gdf))
    return gdf, sig
