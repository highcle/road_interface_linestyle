"""車両（バス）の現在位置。

DB の観測のうち、観測時刻が現在から BUS_RECENT_MINUTES 分以内のものを「現在位置」の候補とし、
次の順に絞り込む。

1. 同じ車両の観測は最新の1点だけにする（走行中の車両は5分間に何十点も記録するため）
2. 互いに BUS_MERGE_DISTANCE_M 以内にある点は1つにまとめ、その中で最新の点を残す
   （車両記号が読めない観測や、同じ場所にいる複数台のアイコンが重ならないように）。
   まとめられた車両は merged に記録する。

観測点そのもの（道路に紐付ける前の緯度経度）を使う。
"""
from datetime import timedelta

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer

import config
from services import db_connector

_to_metric = Transformer.from_crs(4326, config.METRIC_CRS, always_xy=True)
_geod = Geod(ellps="GRS80")


def _bearing(prev, cur):
    """直前の観測からの進行方向（真北=0°, 時計回り）。動いていなければ None。"""
    if prev is None:
        return None
    (lon0, lat0), (lon1, lat1) = prev, cur
    az, _, dist = _geod.inv(lon0, lat0, lon1, lat1)
    if dist < 10:  # 10m 未満は停車中・GPS の揺れとみなす
        return None
    return round(float(az % 360), 0)


def select_bus_positions(obs, minutes=config.BUS_RECENT_MINUTES, merge_m=config.BUS_MERGE_DISTANCE_M):
    """クレンジング済みの観測（期間で抽出済み）から、表示する車両位置を選ぶ。"""
    if obs is None or not len(obs):
        return []
    df = obs.sort_values(["get_at", "obs_id"], ascending=False).reset_index(drop=True)
    x, y = _to_metric.transform(df["longitude"].to_numpy(), df["latitude"].to_numpy())
    df["x"], df["y"] = x, y

    # 1. 車両ごとに最新の1点（車両記号が不明な観測は1点ずつ候補にする）
    known = df["bus"] != "unknown"
    latest = pd.concat([df[known].drop_duplicates("bus"), df[~known]]).sort_values(
        ["get_at", "obs_id"], ascending=False)
    # 進行方向は同じ車両の1つ前の観測から求める
    prev_xy = {}  # 車両 → 1つ前の観測の (経度, 緯度)
    for bus, g in df[known].groupby("bus", sort=False):
        if len(g) >= 2:
            prev_xy[bus] = (g.iloc[1]["longitude"], g.iloc[1]["latitude"])

    # 2. 近くの点をまとめる（新しい順に採用し、採用済みの点から merge_m 以内なら統合）
    kept = []
    for r in latest.itertuples():
        host = next((k for k in kept if np.hypot(k["_x"] - r.x, k["_y"] - r.y) <= merge_m), None)
        if host is not None:
            if r.bus != host["bus"] and r.bus not in host["merged"]:
                host["merged"].append(r.bus)
            continue
        kept.append({
            "_x": r.x, "_y": r.y,
            "bus": r.bus,
            "lat": round(float(r.latitude), 6),
            "lon": round(float(r.longitude), 6),
            "observed_at": r.get_at.strftime(config.TIME_FORMAT),
            "obs_id": int(r.obs_id),
            "wips": None if pd.isna(r.wips) else round(float(r.wips), 3),
            "road_surface": None if pd.isna(r.road_surface) else str(r.road_surface),
            "image_path": None if pd.isna(r.image_path) else str(r.image_path),
            "heading": _bearing(prev_xy.get(r.bus), (r.longitude, r.latitude)) if r.bus != "unknown" else None,
            "merged": [],
        })
    for k in kept:
        del k["_x"], k["_y"]
    return kept


def bus_positions(now=None, minutes=config.BUS_RECENT_MINUTES):
    now = now or config.now()
    obs = db_connector.load_observations(now - timedelta(minutes=minutes), now)
    buses = select_bus_positions(obs, minutes)
    for b in buses:
        b["age_seconds"] = int((now - pd.Timestamp(b["observed_at"])).total_seconds())
    return {
        "now": now.strftime(config.TIME_FORMAT),
        "window_minutes": minutes,
        "merge_distance_m": config.BUS_MERGE_DISTANCE_M,
        "buses": buses,
    }
