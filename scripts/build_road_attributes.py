"""区間ごとに「路線名」と「市町村」を外部データから付与する（オフラインの前処理）。

N13（国土数値情報 道路）には路線番号・路線名の属性が無いため、次の2つと突合する。

  路線名: OpenStreetMap（Geofabrik の北海道抽出 .osm.pbf）
          国道 = highway=trunk の ref、道道 = highway=primary/secondary の ref と name、
          高速 = highway=motorway の name / ref
  市町村: 国土数値情報 行政区域（N03）

結果は data/road_attributes.csv に保存し、アプリ起動時に road_loader が読み込む。
本番サーバーでは外部データは不要（CSV だけあればよい）。道路データ(geojson)を
差し替えたときは、このスクリプトを再実行する。

使い方:
  python scripts/build_road_attributes.py --osm hokkaido-latest.osm.pbf \
      --n03 N03-20250101_01.shp [--out data/road_attributes.csv]

路線の判定方法:
  1. 区間に沿って約 20m ごと（最低3点）に標本点を取る
  2. 各標本点から、道路分類が対応する OSM の道（国道↔trunk/motorway、
     道道↔primary/secondary、高速↔motorway/trunk）のうち最も近いものを 20m 以内で探す
  3. 標本点での区間の向きと OSM の道の向きの差が 30° を超えるものは捨てる（交差道路の除外）
  4. 標本点の 60% 以上が同じ路線を指したときだけ、その路線名を採用する
"""
import argparse
import json
import math
import os
import re
import sys
from datetime import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from services.road_loader import _load_from_geojson  # noqa: E402

SAMPLE_STEP_M = 20
MIN_SAMPLES = 3
MATCH_RADIUS_M = 20
MAX_ANGLE_DEG = 30
MIN_SHARE = 0.6
MUNI_MAX_DIST_M = 500   # 海岸線付近で行政区域ポリゴンの外に出た区間の救済

# N13 の道路分類 → 照合してよい OSM の highway
COMPATIBLE = {
    "1": ("trunk", "motorway"),          # 国道（一般国道の自動車専用道路を含む）
    "2": ("primary", "secondary"),       # 都道府県道
    "4": ("motorway", "trunk"),          # 高速自動車国道等
}

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "road_attributes.csv")


def _tag(s, key):
    if not isinstance(s, str):
        return None
    m = re.search(r'"%s"=>"([^"]*)"' % re.escape(key), s)
    return m.group(1) if m else None


def route_label(highway, ref, name):
    """OSM のタグから表示用の路線名を作る。作れなければ None。"""
    ref = ref if isinstance(ref, str) else ""
    name = name if isinstance(name, str) else ""
    refs = [r.strip() for r in ref.split(";") if r.strip()]
    names = [n.strip() for n in name.split(";") if n.strip()]
    nums = [r for r in refs if r.isdigit()]
    if highway == "trunk":
        return "国道" + "・".join(f"{n}号" for n in nums) if nums else None
    if highway in ("primary", "secondary"):
        if not nums:
            return None
        return f"道道{nums[0]}号" + (f" {names[0]}" if names else "")
    if highway == "motorway":
        ecode = next((r for r in refs if r.startswith("E")), None)
        if names:
            return names[0] + (f"（{ecode}）" if ecode else "")
        return "国道" + "・".join(f"{n}号" for n in nums) if nums else ecode
    return None


def load_osm(pbf):
    df = pyogrio.read_dataframe(
        pbf,
        sql="SELECT osm_id, name, highway, other_tags FROM lines "
            "WHERE highway IN ('motorway','trunk','primary','secondary')",
    )
    df["ref"] = df["other_tags"].map(lambda s: _tag(s, "ref"))
    df["route"] = [route_label(h, r, n) for h, r, n in zip(df.highway, df.ref, df.name)]
    df = df[df.route.notna()].drop(columns=["other_tags"])
    return df.to_crs(config.METRIC_CRS)


def _bearing(p0, p1):
    dx = shapely.get_x(p1) - shapely.get_x(p0)
    dy = shapely.get_y(p1) - shapely.get_y(p0)
    return np.degrees(np.arctan2(dy, dx))


def match_routes(roads_m, osm_m):
    """区間ごとの (route, share) を返す。"""
    geoms = roads_m.geometry.values
    lengths = shapely.length(geoms)
    n = np.maximum(MIN_SAMPLES, np.ceil(lengths / SAMPLE_STEP_M).astype(int))
    seg = np.repeat(np.arange(len(roads_m)), n)
    # 区間内の位置 (i + 0.5) / n
    offs = np.concatenate([(np.arange(k) + 0.5) / k for k in n])
    g = geoms[seg]
    L = lengths[seg]
    d = offs * L
    pts = shapely.line_interpolate_point(g, d)
    h = np.minimum(2.0, L / 4)
    seg_dir = _bearing(shapely.line_interpolate_point(g, d - h), shapely.line_interpolate_point(g, d + h))

    samples = gpd.GeoDataFrame({"seg": seg, "dir": seg_dir, "cls": roads_m.road_class.values[seg]},
                               geometry=pts, crs=roads_m.crs)
    hits = []
    for cls, highways in COMPATIBLE.items():
        s = samples[samples.cls == cls]
        o = osm_m[osm_m.highway.isin(highways)]
        if s.empty or o.empty:
            continue
        j = gpd.sjoin_nearest(s, o[["route", "geometry"]], how="inner", max_distance=MATCH_RADIUS_M)
        way = o.geometry.loc[j["index_right"]].values
        pos = shapely.line_locate_point(way, j.geometry.values)
        osm_dir = _bearing(shapely.line_interpolate_point(way, pos - 2), shapely.line_interpolate_point(way, pos + 2))
        diff = np.abs((j["dir"].values - osm_dir + 90) % 180 - 90)  # 向き（上下線）は問わない
        j = j[diff <= MAX_ANGLE_DEG]
        # 等距離で複数ヒットした標本点は票を等分する
        j = j.reset_index().rename(columns={"index": "sample"})
        j["w"] = 1.0 / j.groupby("sample")["route"].transform("size")
        hits.append(j[["seg", "route", "w"]])

    total = pd.Series(n, index=np.arange(len(roads_m)))
    if not hits:
        return pd.DataFrame({"route": None, "route_share": 0.0}, index=total.index)
    votes = pd.concat(hits).groupby(["seg", "route"])["w"].sum().reset_index()
    votes["share"] = votes["w"] / total.loc[votes.seg].values
    best = votes.sort_values(["seg", "share"], ascending=[True, False]).drop_duplicates("seg").set_index("seg")
    out = pd.DataFrame(index=total.index)
    out["route"] = best["route"].where(best["share"] >= MIN_SHARE)
    out["route_share"] = best["share"].reindex(out.index).fillna(0.0).round(2)
    return out


def match_municipalities(roads_m, n03_path):
    n03 = gpd.read_file(n03_path).to_crs(config.METRIC_CRS)
    n03["municipality"] = n03["N03_004"].fillna("") + n03["N03_005"].fillna("")
    n03["office"] = n03["N03_002"].fillna("")
    mid = gpd.GeoDataFrame(geometry=roads_m.geometry.interpolate(0.5, normalized=True), crs=roads_m.crs)
    j = gpd.sjoin_nearest(mid, n03[["municipality", "office", "geometry"]], how="left",
                          max_distance=MUNI_MAX_DIST_M, distance_col="d")
    j = j.sort_values("d")
    j = j[~j.index.duplicated()].reindex(roads_m.index)
    return j[["municipality", "office"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--osm", required=True, help="OpenStreetMap の .osm.pbf（北海道抽出）")
    ap.add_argument("--n03", required=True, help="国土数値情報 行政区域 N03 の .shp / .geojson")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    print("道路データを読み込み中...")
    roads = _load_from_geojson(config.GEOJSON_DIR, config.TARGET_ROAD_TYPES)
    roads_m = roads.to_crs(config.METRIC_CRS)
    print(f"  {len(roads)} 区間")

    print("OpenStreetMap を読み込み中...")
    osm_m = load_osm(args.osm)
    print(f"  {len(osm_m)} 本の道")
    print("路線を照合中...")
    routes = match_routes(roads_m, osm_m)

    print("市町村を照合中...")
    munis = match_municipalities(roads_m, args.n03)

    # 突合確認用の中点（road_loader.attach_attributes と同じ計算）
    mid = roads_m.geometry.interpolate(0.5, normalized=True).to_crs(roads.crs)
    out = pd.DataFrame({
        "src": roads["src"].values,
        "fidx": roads["fidx"].values,
        "mid_lon": shapely.get_x(mid.values).round(6),
        "mid_lat": shapely.get_y(mid.values).round(6),
        "office": munis["office"].values,
        "municipality": munis["municipality"].values,
        "route": routes["route"].values,
        "route_share": routes["route_share"].values,
    })
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out.to_csv(args.out, index=False)

    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": {
            "osm": {"file": os.path.basename(args.osm),
                    "license": "ODbL 1.0 (© OpenStreetMap contributors)"},
            "n03": {"file": os.path.basename(args.n03),
                    "license": "国土数値情報（行政区域データ）国土交通省 / CC BY 4.0 互換"},
        },
        "params": {"sample_step_m": SAMPLE_STEP_M, "min_samples": MIN_SAMPLES,
                   "match_radius_m": MATCH_RADIUS_M, "max_angle_deg": MAX_ANGLE_DEG,
                   "min_share": MIN_SHARE, "muni_max_dist_m": MUNI_MAX_DIST_M},
        "coverage": {
            "segments": int(len(out)),
            "route": {cls: round(float(out.route[roads.road_class.values == cls].notna().mean()), 3)
                      for cls in sorted(roads.road_class.unique())},
            "municipality": round(float((out.municipality.fillna("") != "").mean()), 3),
        },
    }
    with open(os.path.splitext(args.out)[0] + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta["coverage"], ensure_ascii=False, indent=2))
    print(f"出力: {args.out}")


if __name__ == "__main__":
    main()
