"""直近24時間の観測を道路区間に紐付けてキャッシュする（cron から5分毎に実行）。

出力:
  cache/recent_matched.pkl          紐付け済み観測（app.py が読み込む）
  cache/geometry_<署名>.geojson.gz   配信用道路ジオメトリ（道路データが変わった時のみ生成）
  cache/roads_<署名>.pkl            抽出済み道路データ
"""
import logging
import sys
import time

import config
from services.matcher import RoadMatcher
from services.road_loader import load_roads
from services.status_service import build_geometry_file, compute_recent, write_recent_cache

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("generate_cache")


def main():
    t0 = time.monotonic()
    start, end = config.default_live_range()
    log.info("直近キャッシュ生成開始 (%s 〜 %s)", start, end)

    roads, sig = load_roads()
    build_geometry_file(roads, sig)
    data = compute_recent(RoadMatcher(roads), sig, start, end)
    write_recent_cache(data)

    m = data["matched"]
    log.info("出力完了: 観測 %d 件 / 紐付け %d 件 / データあり %d 区間 (%.1f 秒)",
             data["n_observations"], len(m), m["seg_id"].nunique() if len(m) else 0,
             time.monotonic() - t0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("キャッシュ生成に失敗しました")
        sys.exit(1)
