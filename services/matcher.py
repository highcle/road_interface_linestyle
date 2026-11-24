"""観測点を最寄りの道路区間へ紐付ける（空間結合）。"""
import logging

import geopandas as gpd
import pandas as pd

import config

log = logging.getLogger(__name__)

MATCHED_COLUMNS = ["obs_id", "seg_id", "get_at", "wips", "road_surface", "image_path", "bus", "dist_m"]


class RoadMatcher:
    """道路を平面直角座標に投影した状態で保持し、観測点を紐付ける。"""

    def __init__(self, gdf_roads, max_distance_m=config.MATCH_DISTANCE_M, metric_crs=config.METRIC_CRS):
        self.max_distance_m = max_distance_m
        self.metric_crs = metric_crs
        self.roads_m = gdf_roads[["geometry"]].to_crs(epsg=metric_crs)
        self.roads_m.sindex  # 空間インデックスを先に構築しておく

    def match(self, df_obs):
        """観測 DataFrame に seg_id と dist_m を付けて返す。

        max_distance_m より遠い観測（対象外の道路を走行中など）は除外する。
        等距離で複数区間に該当した場合は区間IDの小さい方に寄せる（1観測=1区間）。
        """
        if df_obs is None or len(df_obs) == 0:
            return pd.DataFrame(columns=MATCHED_COLUMNS)

        pts = gpd.GeoDataFrame(
            df_obs,
            geometry=gpd.points_from_xy(df_obs["longitude"], df_obs["latitude"]),
            crs="EPSG:4326",
        ).to_crs(epsg=self.metric_crs)

        joined = gpd.sjoin_nearest(
            pts, self.roads_m, how="inner",
            max_distance=self.max_distance_m, distance_col="dist_m",
        )
        # geopandas は右側 index 名（seg_id）か index_right を列名に使う
        right = "index_right" if "index_right" in joined.columns else "seg_id"
        joined["seg_id"] = joined[right].astype(int)
        joined = (joined.sort_values(["obs_id", "seg_id"])
                        .drop_duplicates("obs_id", keep="first"))

        out = pd.DataFrame(joined[MATCHED_COLUMNS]).sort_values(["get_at", "obs_id"]).reset_index(drop=True)
        log.info("観測 %d 件のうち %d 件を %d 区間に紐付けました（%.0fm 以内）",
                 len(df_obs), len(out), out["seg_id"].nunique(), self.max_distance_m)
        return out
