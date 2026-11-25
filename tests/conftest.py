"""テスト用の小さな道路データと観測 DB を作り、環境変数で差し替える。

config は import 時に環境変数を読むため、プロジェクトのモジュールより先にここで設定する。
"""
import json
import math
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="winterroad_test_")
GEOJSON_DIR = os.path.join(WORK, "geojson")
DB_PATH = os.path.join(WORK, "test.db")
CACHE_DIR = os.path.join(WORK, "cache")
ATTRIBUTES_PATH = os.path.join(WORK, "road_attributes.csv")
FIXED_NOW = "2026-01-10 12:00:00"

os.environ.update({
    "GEOJSON_DIR": GEOJSON_DIR,
    "DB_PATH": DB_PATH,
    "CACHE_DIR": CACHE_DIR,
    "ROAD_ATTRIBUTES_PATH": ATTRIBUTES_PATH,
    "APP_FIXED_NOW": FIXED_NOW,
    "APP_PREFIX": "/WinterRoad-Overview-LineStyle",
})

# ---- 道路: 札幌付近の東西方向の線分 ------------------------------------------
# seg_id はファイル内の対象道路の順番（0,1,2）。N13_003=3（市区町村道）は対象外。
ROADS = [
    ("1", "4", [(141.300, 43.000), (141.310, 43.000)]),   # seg 0: 国道
    ("2", "3", [(141.300, 43.010), (141.310, 43.010)]),   # seg 1: 都道府県道（約1.1km 北）
    ("3", "2", [(141.300, 43.020), (141.310, 43.020)]),   # 対象外（市区町村道）
    ("4", "5", [(141.320, 43.000), (141.330, 43.000)]),   # seg 2: 高速
]

# 道路から約11m 北にずらした観測点の緯度
OFF = 0.0001


def _obs(t, lat, lon, wips, surface, bus, frame=1):
    d = t[8:10] + t[5:7] + t[2:4]
    hms = t[11:13] + t[14:16] + t[17:19]
    return (lat, lon, t, wips, f"image_{d}_{hms}_{frame}_bus_{bus}.jpg", surface)


OBSERVATIONS = [
    # seg 0: 車両A の古い通過（WIPS が低い）→ 最新ではないので代表点にならない
    _obs("2026-01-10 08:00:00", 43.000 + OFF, 141.302, 5.0, "ice", "A"),
    _obs("2026-01-10 08:00:20", 43.000 + OFF, 141.304, 5.5, "ice", "A"),
    # seg 0: 車両A の最新の通過（3観測、最小 8.2 が代表点）
    _obs("2026-01-10 11:00:00", 43.000 + OFF, 141.301, 9.0, "dry", "A"),
    _obs("2026-01-10 11:00:15", 43.000 + OFF, 141.303, 8.2, "wet", "A"),
    _obs("2026-01-10 11:00:30", 43.000 + OFF, 141.305, 9.5, "dry", "A"),
    # seg 1: 同時刻に2台が通過 → WIPS の低い方の通過を採用
    _obs("2026-01-10 10:00:00", 43.010 + OFF, 141.302, 9.1, "dry", "B"),
    _obs("2026-01-10 10:00:00", 43.010 + OFF, 141.303, 7.0, "slush", "C"),
    # seg 2: 最新通過の WIPS がすべて異常値（-Inf）→ 最新観測を代表点、WIPS は欠損
    _obs("2026-01-10 09:00:00", 43.000 + OFF, 141.322, 9.0, "dry", "D"),
    _obs("2026-01-10 11:30:00", 43.000 + OFF, 141.322, -math.inf, "fresh", "D"),
    _obs("2026-01-10 11:30:10", 43.000 + OFF, 141.324, -math.inf, "fresh", "D"),
    # 対象外の道路の近く（どの対象道路からも 50m 超）→ 紐付けない
    _obs("2026-01-10 11:00:00", 43.020 + OFF, 141.305, 3.0, "ice", "E"),
    # 時刻が不正
    (43.000 + OFF, 141.302, "not-a-time", 9.0, "image_x.jpg", "dry"),
    # 車両の現在位置用（道路から離れた場所）: F が北へ移動、その近くに G（最新）。H は5分より前
    _obs("2026-01-10 11:57:00", 43.0500, 141.350, 9.0, "dry", "F"),
    _obs("2026-01-10 11:58:00", 43.0505, 141.350, 9.0, "dry", "F"),
    _obs("2026-01-10 11:59:00", 43.0506, 141.3502, 8.0, "wet", "G"),
    _obs("2026-01-10 11:50:00", 43.1000, 141.400, 9.0, "dry", "H"),
    # 24時間より前（現在モードの範囲外）
    _obs("2026-01-08 11:00:00", 43.000 + OFF, 141.302, 2.0, "ice", "A"),
]


def _build():
    os.makedirs(GEOJSON_DIR, exist_ok=True)
    features = [
        {"type": "Feature",
         "properties": {"N13_001": "2020-01-01", "N13_002": "1", "N13_003": cls, "N13_004": "1",
                        "N13_005": 0, "N13_006": width, "N13_007": "1", "N13_008": "644100"},
         "geometry": {"type": "LineString", "coordinates": coords}}
        for cls, width, coords in ROADS
    ]
    with open(os.path.join(GEOJSON_DIR, "N13-test.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    # 路線名・市町村: seg 0 は正しく突合できる行、seg 1 は位置がずれた行（使われない）、seg 2 は行なし
    import geopandas as gpd
    from shapely.geometry import LineString
    lines = gpd.GeoSeries([LineString(c) for _, _, c in ROADS], crs="EPSG:6668")
    mid = lines.to_crs(6679).interpolate(0.5, normalized=True).to_crs(6668)
    with open(ATTRIBUTES_PATH, "w", encoding="utf-8") as f:
        f.write("src,fidx,mid_lon,mid_lat,office,municipality,route,route_share\n")
        f.write(f"N13-test.geojson,0,{mid.x[0]:.6f},{mid.y[0]:.6f},石狩振興局,札幌市南区,国道5号,1.0\n")
        f.write(f"N13-test.geojson,1,{mid.x[1] + 0.001:.6f},{mid.y[1]:.6f},石狩振興局,札幌市南区,道道1号 テスト線,1.0\n")

    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE pointed_road_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT, latitude FLOAT, longitude FLOAT,
            get_at DATETIME, WIPS REAL, image_path TEXT, road_surface TEXT,
            mesh_1km_id INTEGER, mesh_10km_id INTEGER);
    """)
    conn.executemany(
        "INSERT INTO pointed_road_data (latitude, longitude, get_at, WIPS, image_path, road_surface) VALUES (?,?,?,?,?,?)",
        OBSERVATIONS,
    )
    conn.commit()
    conn.close()


_build()


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    import generate_cache
    generate_cache.main()
    import app as app_module
    return app_module.app.test_client()
