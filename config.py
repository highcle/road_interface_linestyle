import os
from datetime import datetime, timedelta

GEOJSON_DIR = os.getenv("GEOJSON_DIR", "./geojson")
DB_PATH = os.getenv("DB_PATH", "./database.db")

# 抽出対象の道路種別 (N13_003: 1=高速, 2=一般国道, 4=主要地方道)
TARGET_ROAD_TYPES = {'1', '2', '4'}

# デフォルトの検索時間幅 (直近24時間)
DEFAULT_TIME_HOURS = 24

def get_default_time_range():
    now = datetime.now()
    start = now - timedelta(hours=DEFAULT_TIME_HOURS)
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")