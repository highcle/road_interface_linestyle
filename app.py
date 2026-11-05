import os
import json
from flask import Flask, render_template, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from config import GEOJSON_DIR, DB_PATH, TARGET_ROAD_TYPES, get_default_time_range
from services.road_loader import load_and_filter_roads
from services.db_connector import load_db_data
from services.aggregator import link_and_aggregate

app = Flask(__name__)

# ★ サブパス (/WinterRoad-Overview-LineStyle) を強制セットするミドルウェア
class PrefixMiddleware:
    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        environ['SCRIPT_NAME'] = self.prefix
        return self.app(environ, start_response)

# Apacheを変更せず、アプリ側でプレフィックスを強制指定
app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/WinterRoad-Overview-LineStyle')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON_PATH = os.path.join(BASE_DIR, "output_24h.json")

print("ベース道路ベクターデータをロード中...")
GDF_ROADS = load_and_filter_roads(GEOJSON_DIR, TARGET_ROAD_TYPES)
print("ロード完了。")

@app.route("/")
def index():
    default_start, default_end = get_default_time_range()
    return render_template("index.html", default_start=default_start, default_end=default_end)

@app.route("/api/roads/recent", methods=["GET"])
def get_recent_roads():
    if os.path.exists(OUTPUT_JSON_PATH):
        with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
            
    return jsonify({"type": "FeatureCollection", "features": []})

@app.route("/api/roads/search", methods=["GET"])
def search_roads_history():
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    gdf_obs = load_db_data(DB_PATH, start_time, end_time)
    result_gdf = link_and_aggregate(GDF_ROADS, gdf_obs)
    return jsonify(json.loads(result_gdf.to_json()))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, debug=False)