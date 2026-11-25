"""旧API（/api/roads/recent, /api/roads/search）の互換出力。

画面は /api/roads/status と /api/roads/geometry を使うが、他のシステムが旧APIを
使っている可能性があるため、レスポンスの形を旧実装に合わせて残している。

旧実装との違い（いずれも旧実装の不具合の修正）:
  - WIPS の非有限値（-Inf など）は集計から除く。旧実装では平均が -Inf になり、
    JSON として不正なレスポンスになっていた
  - display_route_name は路線名（例: 国道5号）。旧実装は幅員区分の番号（"2" など）を
    返していた。路線名が分からない区間は道路分類（幅員）
  - road_surface は小文字に揃えた値
集計方法は旧実装のまま: WIPS は期間内の平均、それ以外は期間内の最後の観測。
"""
import json

import pandas as pd

import config
from services.road_loader import N13_KEYS


def aggregate(matched):
    """区間ごとに旧実装と同じ集計をする。"""
    if matched is None or not len(matched):
        return pd.DataFrame(columns=["wips", "road_surface", "last_updated", "image_path"])
    m = matched.sort_values(["get_at", "obs_id"])
    g = m.groupby("seg_id")
    last = g.tail(1).set_index("seg_id")
    return pd.DataFrame({
        "wips": g["wips"].mean().round(2),
        "road_surface": last["road_surface"],
        "last_updated": g["get_at"].max().dt.strftime(config.TIME_FORMAT),
        "image_path": last["image_path"],
    })


def _value(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def feature_collection(roads_wgs84, matched):
    """全区間（データなしを含む）の GeoJSON を JSON 文字列で返す。"""
    agg = aggregate(matched)
    agg_rows = agg.to_dict("index")
    empty = {"wips": None, "road_surface": None, "last_updated": None, "image_path": None}
    features = []
    for seg_id, row in zip(roads_wgs84.index, roads_wgs84.itertuples()):
        props = {k: _value(getattr(row, k)) for k in N13_KEYS}
        props["display_route_name"] = row.label
        a = agg_rows.get(seg_id, empty)
        props.update({k: _value(a[k]) for k in empty})
        features.append({"type": "Feature", "id": str(seg_id), "properties": props,
                         "geometry": row.geometry.__geo_interface__})
    return json.dumps({"type": "FeatureCollection", "features": features},
                      ensure_ascii=False, allow_nan=False)
