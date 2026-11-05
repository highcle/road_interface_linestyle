import geopandas as gpd

def link_and_aggregate(gdf_roads, gdf_obs):
    """
    最寄りの道路へ空間結合して集計。データがない路線も灰色で表示するために維持する。
    """
    print("3/4: 空間結合（最寄り道路への紐付け・集計）...")
    
    # 元の道路データをコピー
    result_roads = gdf_roads.copy()
    result_roads["wips"] = None
    result_roads["road_surface"] = None
    result_roads["last_updated"] = None
    result_roads["image_path"] = None

    if gdf_obs is not None and len(gdf_obs) > 0:
        # メートル単位計算用（北海道平面直角座標系: EPSG 6679）に一時変換
        gdf_roads_m = gdf_roads.to_crs(epsg=6679)
        gdf_obs_m = gdf_obs.to_crs(epsg=6679)

        # 観測点に最も近い道路セグメントを検索
        joined = gpd.sjoin_nearest(gdf_obs_m, gdf_roads_m, how="inner", distance_col="dist_m")
        joined = joined[joined["dist_m"] <= 50]  # 50m超の離脱点を除外

        if len(joined) > 0:
            aggregated = joined.groupby("index_right").agg({
                "wips": "mean",
                "road_surface": lambda x: x.iloc[-1],
                "get_at": "max",
                "image_path": lambda x: x.iloc[-1]
            }).reset_index()

            for _, row in aggregated.iterrows():
                idx = int(row["index_right"])
                result_roads.loc[idx, "wips"] = round(row["wips"], 2)
                result_roads.loc[idx, "road_surface"] = row["road_surface"]
                result_roads.loc[idx, "last_updated"] = str(row["get_at"])
                result_roads.loc[idx, "image_path"] = str(row["image_path"])

    # データのないセグメントも含めた全道路データを WGS84(EPSG:4326) で返す
    all_roads = result_roads.to_crs(epsg=4326)
    linked_count = len(result_roads[result_roads["wips"].notnull()])
    print(f"   -> 総セグメント数: {len(all_roads)} 件（データ紐付けあり: {linked_count} 件, データなし: {len(all_roads) - linked_count} 件）")
    return all_roads