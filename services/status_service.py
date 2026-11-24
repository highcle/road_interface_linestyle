"""画面に返す「区間ごとの状態」を組み立てる。

- 現在モード: generate_cache.py が5分毎に作る「直近24時間の紐付け済み観測」(cache/recent_matched.pkl)
  を読み、指定範囲で代表点を選ぶ。DB にも空間結合にも触れないので高速。
- 過去モード: 指定期間を DB から取得・紐付けし、結果をメモリにキャッシュする。
  負荷対策として期間上限・同時実行数制限を設ける。
"""
import gzip
import json
import logging
import os
import pickle
import threading
from collections import OrderedDict
from datetime import datetime, timedelta

import pandas as pd
import shapely

import config
from services import db_connector, representative
from services.matcher import RoadMatcher
from services.road_loader import load_roads

log = logging.getLogger(__name__)

RECENT_CACHE = os.path.join(config.CACHE_DIR, "recent_matched.pkl")


class BusyError(Exception):
    """過去検索の同時実行数が上限に達した。"""


class ValidationError(ValueError):
    pass


def parse_time(s, name):
    if not s:
        raise ValidationError(f"{name} を指定してください（形式: YYYY-MM-DD HH:MM:SS）")
    s = s.strip().replace("T", " ")
    for fmt in (config.TIME_FORMAT, "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ValidationError(f"{name} の形式が不正です: {s}（形式: YYYY-MM-DD HH:MM:SS）")


def image_url(image_path, prefix):
    """画像ファイル名から配信URLを作る。命名規則に合わなければ None。"""
    info = db_connector.parse_image_name(image_path)
    if not info:
        return None
    return f"{prefix}/static/images/_indicated_bus_{info['bus']}/{info['date']}/{image_path}"


def build_geometry_file(gdf_roads, signature, cache_dir=config.CACHE_DIR):
    """配信用の道路ジオメトリ (GeoJSON, gzip) を作る。存在すれば何もしない。"""
    path = os.path.join(cache_dir, f"geometry_{signature}.geojson.gz")
    if os.path.exists(path):
        return path
    g = gdf_roads.to_crs(epsg=4326)
    g = g.set_geometry(shapely.set_precision(g.geometry.values, 10 ** -config.GEOMETRY_PRECISION))
    features = [
        {
            "type": "Feature",
            "properties": {"id": int(seg_id), "label": row.label, "road_class": row.road_class},
            "geometry": shapely.geometry.mapping(row.geometry),
        }
        for seg_id, row in zip(g.index, g.itertuples())
    ]
    body = json.dumps({"type": "FeatureCollection", "signature": signature, "features": features},
                      ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        f.write(body)
    os.replace(tmp, path)
    log.info("配信用ジオメトリを生成しました: %s", path)
    return path


def compute_recent(matcher, signature, start, end):
    obs = db_connector.load_observations(start, end)
    matched = matcher.match(obs)
    return {
        "signature": signature,
        "window_start": start,
        "window_end": end,
        "generated_at": config.now(),
        "n_observations": int(len(obs)),
        "matched": matched,
    }


def write_recent_cache(data, path=RECENT_CACHE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)  # アトミックに置換（読み込み中の破損防止）


class StatusService:
    def __init__(self):
        self.roads, self.signature = load_roads()
        self.matcher = RoadMatcher(self.roads)
        self.geometry_path = build_geometry_file(self.roads, self.signature)
        self._recent = None
        self._recent_mtime = None
        self.signature_mismatch = False
        self._lock = threading.Lock()
        self._search_sem = threading.BoundedSemaphore(config.MAX_CONCURRENT_SEARCHES)
        self._search_cache = OrderedDict()
        self.has_time_index = db_connector.has_time_index()
        if not self.has_time_index:
            log.warning("pointed_road_data.get_at にインデックスがありません。"
                        "検索が遅くなります（scripts/create_indexes.sql 参照）")

    # ---- 現在モード ------------------------------------------------------
    def recent(self):
        """直近24時間キャッシュ。ファイルが更新されていれば読み直す。"""
        with self._lock:
            mtime = os.path.getmtime(RECENT_CACHE) if os.path.exists(RECENT_CACHE) else None
            if mtime is not None and mtime != self._recent_mtime:
                with open(RECENT_CACHE, "rb") as f:
                    data = pickle.load(f)
                self._recent_mtime = mtime  # 同じファイルを何度も読み直さない
                if data.get("signature") != self.signature:
                    # 道路データが更新された（区間IDが変わる）→ アプリの再起動が必要
                    self.signature_mismatch = True
                    log.error("キャッシュの道路データ(%s)が起動時のもの(%s)と異なります。アプリを再起動してください",
                              data.get("signature"), self.signature)
                else:
                    self.signature_mismatch = False
                    data["source"] = "cache"
                    self._recent = data
            if self._recent is None:
                # キャッシュ未生成（初回起動など）: その場で計算して保持する
                log.warning("直近キャッシュがないため DB から直接計算します（generate_cache.py の cron 設定を確認）")
                start, end = config.default_live_range()
                data = self._guarded(lambda: compute_recent(self.matcher, self.signature, start, end))
                data["source"] = "db"
                self._recent, self._recent_mtime = data, None
            return self._recent

    # ---- 過去モード ------------------------------------------------------
    def _guarded(self, fn):
        if not self._search_sem.acquire(blocking=False):
            raise BusyError("他の検索を処理中です。しばらくしてから再度お試しください")
        try:
            return fn()
        finally:
            self._search_sem.release()

    def history(self, start, end):
        key = (start, end)
        with self._lock:
            if key in self._search_cache:
                self._search_cache.move_to_end(key)
                return self._search_cache[key]
        data = self._guarded(lambda: compute_recent(self.matcher, self.signature, start, end))
        data["source"] = "history"
        with self._lock:
            self._search_cache[key] = data
            while len(self._search_cache) > config.SEARCH_CACHE_SIZE:
                self._search_cache.popitem(last=False)
        return data

    @staticmethod
    def validate_history_range(start, end):
        if start >= end:
            raise ValidationError("開始日時は終了日時より前にしてください")
        if end - start > timedelta(days=config.MAX_SEARCH_DAYS):
            raise ValidationError(f"検索期間は最大 {config.MAX_SEARCH_DAYS} 日までです")
        if start > config.now():
            raise ValidationError("未来の日時は検索できません")

    # ---- 共通 ------------------------------------------------------------
    def base_data(self, base_start=None, base_end=None):
        """base 指定なし→現在モード、あり→過去モード。"""
        if base_start is None and base_end is None:
            return "live", self.recent()
        if base_start is None or base_end is None:
            raise ValidationError("base_start と base_end は両方指定してください")
        self.validate_history_range(base_start, base_end)
        return "history", self.history(base_start, base_end)

    def status(self, prefix, base_start=None, base_end=None, start=None, end=None):
        if start and end and start >= end:
            raise ValidationError("表示範囲の開始は終了より前にしてください")
        mode, data = self.base_data(base_start, base_end)
        w_start, w_end = data["window_start"], data["window_end"]
        start = max(start or w_start, w_start)
        end = min(end or w_end, w_end)
        if start > end:
            # 表示範囲が期間の外に出た（時間の経過で期間が進んだ等）→ 期間全体に戻す
            start, end = w_start, w_end

        matched = data["matched"]
        segments = representative.select_representatives(matched, start, end)
        for rep in segments.values():
            rep["image_url"] = image_url(rep.pop("image_path"), prefix)

        now = config.now()
        gen = data["generated_at"]
        latest = matched["get_at"].max() if len(matched) else None
        fmt = lambda t: None if t is None or pd.isna(t) else pd.Timestamp(t).strftime(config.TIME_FORMAT)
        return {
            "mode": mode,
            "source": data.get("source"),
            "algorithm": representative.ALGORITHM,
            "now": fmt(now),
            "generated_at": fmt(gen),
            "cache_stale": mode == "live" and (now - gen) > timedelta(minutes=config.CACHE_STALE_MINUTES),
            "window": {"start": fmt(w_start), "end": fmt(w_end)},
            "range": {"start": fmt(start), "end": fmt(end)},
            "latest_observation_at": fmt(latest),
            "counts": {
                "observations_in_window": data.get("n_observations"),
                "matched_in_window": int(len(matched)),
                "segments_with_data": len(segments),
            },
            "thresholds": {"wips_danger_max": config.WIPS_DANGER_MAX, "wips_warn_max": config.WIPS_WARN_MAX},
            "segments": segments,
        }

    def timeline(self, seg_id, base_start=None, base_end=None, start=None, end=None):
        _, data = self.base_data(base_start, base_end)
        start = max(start or data["window_start"], data["window_start"])
        end = min(end or data["window_end"], data["window_end"])
        return representative.segment_timeline(data["matched"], seg_id, start, end)

    def health(self):
        out = {"status": "ok", "now": config.now().strftime(config.TIME_FORMAT),
               "db_time_index": self.has_time_index, "road_segments": int(len(self.roads))}
        if os.path.exists(RECENT_CACHE):
            with open(RECENT_CACHE, "rb") as f:
                d = pickle.load(f)
            age = (config.now() - d["generated_at"]).total_seconds() / 60
            out["cache_generated_at"] = d["generated_at"].strftime(config.TIME_FORMAT)
            out["cache_age_minutes"] = round(age, 1)
            if age > config.CACHE_STALE_MINUTES:
                out["status"] = "stale"
        else:
            out["status"] = "no_cache"
        if self.signature_mismatch:
            out["status"] = "restart_required"
        return out
