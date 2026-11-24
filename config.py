"""アプリ全体の設定値。

環境変数で上書きできる値は、本番・開発・テストで切り替える想定のもの。
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _path(env, default):
    p = os.getenv(env, default)
    return p if os.path.isabs(p) else os.path.join(BASE_DIR, p)


# ---- パス ---------------------------------------------------------------
GEOJSON_DIR = _path("GEOJSON_DIR", "geojson")
DB_PATH = _path("DB_PATH", "database.db")
CACHE_DIR = _path("CACHE_DIR", "cache")

# ---- Web ----------------------------------------------------------------
# Apache の公開パス。プレフィックスの有無どちらの URL でもアクセスできる。
APP_PREFIX = os.getenv("APP_PREFIX", "/WinterRoad-Overview-LineStyle").rstrip("/")
HOST = os.getenv("APP_HOST", "0.0.0.0")
PORT = int(os.getenv("APP_PORT", "5100"))

# ---- 時刻 ---------------------------------------------------------------
# DB の get_at はタイムゾーン情報なしの日本時間として扱う。
TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Tokyo"))
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# テスト用: 基準時刻を固定する（例: APP_FIXED_NOW="2026-11-05 12:30:00"）。
# 本番では未設定にすること（未設定なら現在時刻）。
FIXED_NOW = os.getenv("APP_FIXED_NOW") or None


def now():
    """基準となる「現在時刻」(タイムゾーンなし、日本時間)。"""
    if FIXED_NOW:
        return datetime.strptime(FIXED_NOW, TIME_FORMAT)
    return datetime.now(TIMEZONE).replace(tzinfo=None, microsecond=0)


# ---- 道路データ ---------------------------------------------------------
# 国土数値情報 道路(N13) N13_003「道路分類」:
#   1=国道, 2=都道府県道, 3=市区町村道等, 4=高速自動車国道等, 5=その他, 6=不明
TARGET_ROAD_TYPES = {"1", "2", "4"}
ROAD_CLASS_LABELS = {
    "1": "国道", "2": "都道府県道", "3": "市区町村道等",
    "4": "高速自動車国道等", "5": "その他", "6": "不明",
}
# N13_006「幅員区分」
ROAD_WIDTH_LABELS = {
    "1": "幅員3m未満", "2": "幅員3〜5.5m", "3": "幅員5.5〜13m",
    "4": "幅員13〜19.5m", "5": "幅員19.5m以上", "6": "幅員不明",
}
# 座標を丸める桁数（小数6桁 ≒ 0.1m）。配信サイズ削減用。
GEOMETRY_PRECISION = 6

# ---- 観測データ ---------------------------------------------------------
LIVE_WINDOW_HOURS = 24          # 「現在」モードで扱う時間幅
CACHE_STALE_MINUTES = 15        # キャッシュがこれより古ければ画面に警告
MAX_SEARCH_DAYS = 7             # 過去検索で一度に指定できる最大日数
MATCH_DISTANCE_M = 50.0         # 観測点→道路の紐付け最大距離 [m]
METRIC_CRS = 6679               # 距離計算用 平面直角座標系（JGD2011 第XI系）

# WIPS の有効範囲。範囲外の値は「WIPS 欠損」として扱う（路面状態は残す）。
# 非有限値(±Inf, NaN)は常に欠損扱い。None は制限なし。
# 例: bus_K の 2026/04〜09 は 14〜16 付近に分布しており、他車両と尺度が異なる可能性がある。
WIPS_VALID_MIN = float(os.getenv("WIPS_VALID_MIN")) if os.getenv("WIPS_VALID_MIN") else None
WIPS_VALID_MAX = float(os.getenv("WIPS_VALID_MAX")) if os.getenv("WIPS_VALID_MAX") else None

# WIPS を欠損扱いにする車両（カンマ区切り、例: WIPS_EXCLUDED_BUSES="J,K"）。
# カメラの汚れ・故障などで WIPS が信頼できない車両を一時的に除外する。路面状態は残す。
WIPS_EXCLUDED_BUSES = {b.strip() for b in os.getenv("WIPS_EXCLUDED_BUSES", "").split(",") if b.strip()}

# WIPS の判定閾値（画面の色分けと一致させる）
WIPS_DANGER_MAX = 7.5   # これ以下: 視程不良（危険）
WIPS_WARN_MAX = 8.0     # これ未満: 注意

# ---- 代表点選出 ---------------------------------------------------------
# 同一車両の観測がこの時間以上空いたら別の「通過」とみなす [分]
PASS_GAP_MINUTES = 10

# ---- 過去検索の負荷対策 -------------------------------------------------
MAX_CONCURRENT_SEARCHES = 2
SEARCH_CACHE_SIZE = 8


def default_live_range():
    end = now()
    return end - timedelta(hours=LIVE_WINDOW_HOURS), end
