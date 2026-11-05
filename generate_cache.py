import os
import json
import time
from config import GEOJSON_DIR, DB_PATH, TARGET_ROAD_TYPES, get_default_time_range
from services.road_loader import load_and_filter_roads
from services.db_connector import load_db_data
from services.aggregator import link_and_aggregate

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON_PATH = os.path.join(BASE_DIR, "output_24h.json")
TEMP_JSON_PATH = os.path.join(BASE_DIR, "output_24h.json.tmp")

def main():
    start_time, end_time = get_default_time_range()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 24時間データキャッシュ生成開始 ({start_time} ～ {end_time})")

    # 1. 道路ベクターの読み込み
    gdf_roads = load_and_filter_roads(GEOJSON_DIR, TARGET_ROAD_TYPES)

    # 2. DBから観測データを取得
    gdf_obs = load_db_data(DB_PATH, start_time, end_time)

    # 3. 空間結合・集計
    result_gdf = link_and_aggregate(gdf_roads, gdf_obs)
    cache_data = json.loads(result_gdf.to_json())

    # 4. 一時ファイルへ書き出してからアトミック置換 (読み込み中のファイル破損を防ぐ)
    with open(TEMP_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False)
    
    os.replace(TEMP_JSON_PATH, OUTPUT_JSON_PATH)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 出力完了: '{OUTPUT_JSON_PATH}'")

if __name__ == "__main__":
    main()