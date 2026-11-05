import os
from flask import Flask, render_template, request, jsonify, send_from_directory
import json
from config import GEOJSON_DIR, DB_PATH, TARGET_ROAD_TYPES, get_default_time_range
from services.road_loader import load_and_filter_roads
from services.db_connector import load_db_data
from services.aggregator import link_and_aggregate

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.getenv("IMAGE_DIR", "./images")
OUTPUT_JSON_PATH = os.path.join(BASE_DIR, "output_24h.json")

# 過去指定（オンデマンド検索）時用に道路ベースベクターのみメモリ保持
print("ベース道路ベクターデータをロード中...")
GDF_ROADS = load_and_filter_roads(GEOJSON_DIR, TARGET_ROAD_TYPES)
print("ロード完了。")

@app.route("/")
def index():
    default_start, default_end = get_default_time_range()
    return render_template("index.html", default_start=default_start, default_end=default_end)

@app.route("/api/roads/recent", methods=["GET"])
def get_recent_roads():
    """cronが生成した output_24h.json を読み込んで爆速返却"""
    if os.path.exists(OUTPUT_JSON_PATH):
        with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
            
    return jsonify({"type": "FeatureCollection", "features": []})

@app.route("/api/roads/search", methods=["GET"])
def search_roads_history():
    """過去指定（カレンダー検索）時のオンデマンドDB検索"""
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    gdf_obs = load_db_data(DB_PATH, start_time, end_time)
    result_gdf = link_and_aggregate(GDF_ROADS, gdf_obs)
    return jsonify(json.loads(result_gdf.to_json()))

@app.route("/images/<path:filename>")
def get_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)