import os
import glob
import json
import re
import geopandas as gpd

def format_route_name(props):
    """
    属性情報から「国道〜号」「〜〜道」の正式名称を抽出・整形する関数
    """
    # 優先属性キーの検索
    raw_name = props.get("N13_006") or props.get("N06_006") or props.get("N06_007") or ""
    
    if not raw_name:
        return "対象道路"

    # 正規表現による路線名の抽出
    # 例: "国道12号", "道央自動車道", "道道1号小樽定山渓線"
    national_match = re.search(r'(国道\s*\d+\s*号)', raw_name)
    if national_match:
        return national_match.group(1).replace(" ", "")

    express_match = re.search(r'([^\s]+自動車道|[^\s]+道)', raw_name)
    if express_match:
        return express_match.group(1)

    return raw_name

def load_and_filter_roads(geojson_dir, target_types):
    search_patterns = [
        os.path.join(geojson_dir, "**", "*.geojson"),
        os.path.join(geojson_dir, "**", "*.json")
    ]
    file_list = []
    for p in search_patterns:
        file_list.extend(glob.glob(p, recursive=True))
    
    features = []
    for fpath in sorted(list(set(file_list))):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
                for item in items:
                    props = item.get("properties", {})
                    if str(props.get("N13_003")) in target_types:
                        # 路線名を人間が読みやすい形式に整形してプロパティに上書き
                        props["display_route_name"] = format_route_name(props)
                        item["properties"] = props
                        features.append(item)
        except Exception:
            continue

    feature_collection = {"type": "FeatureCollection", "features": features}
    gdf_roads = gpd.GeoDataFrame.from_features(feature_collection)
    gdf_roads.crs = "EPSG:6668"
    return gdf_roads