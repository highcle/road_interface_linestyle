"""観測データ (pointed_road_data) の取得とクレンジング。

DB は他システムと共有しているため読み取り専用で開き、スキーマは変更しない。
"""
import logging
import re
import sqlite3
from contextlib import closing

import numpy as np
import pandas as pd

import config

log = logging.getLogger(__name__)

# image_<DDMMYY>_<HHMMSS>_<カメラ/フレーム番号>_bus_<車両記号>.jpg
IMAGE_RE = re.compile(r"^image_(?P<date>\d{6})_(?P<time>\d{6})_(?P<frame>\d+)_bus_(?P<bus>[A-Za-z0-9]+)\.jpe?g$")

COLUMNS = ["obs_id", "latitude", "longitude", "get_at", "wips", "road_surface", "image_path"]


def connect(db_path=config.DB_PATH):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)


def has_time_index(db_path=config.DB_PATH):
    """get_at を先頭列に持つインデックスがあるか。"""
    try:
        with closing(connect(db_path)) as conn:
            for _, name, *_ in conn.execute("PRAGMA index_list(pointed_road_data)"):
                cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{name}')")]
                if cols and cols[0] == "get_at":
                    return True
    except sqlite3.Error as e:
        log.warning("インデックスの確認に失敗しました: %s", e)
    return False


def parse_image_name(name):
    m = IMAGE_RE.match(name or "")
    return m.groupdict() if m else None


def clean_observations(df):
    """型の正規化と異常値の処理。

    - get_at を datetime に変換（変換できない行は除外）
    - WIPS の非有限値（±Inf, NaN）と有効範囲外の値は NaN（=WIPS 欠損）にする。
      路面状態や画像は有効なので行自体は残す。
    - 緯度経度が欠損/0 の行は除外
    - 車両記号を image_path から抽出
    """
    df = df.copy()
    df["get_at"] = pd.to_datetime(df["get_at"], errors="coerce", format="mixed")
    df["wips"] = pd.to_numeric(df["wips"], errors="coerce").astype(float)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    bad_time = df["get_at"].isna()
    bad_pos = df["latitude"].isna() | df["longitude"].isna() | (df["latitude"] == 0) | (df["longitude"] == 0)
    df = df[~bad_time & ~bad_pos]

    wips = df["wips"].to_numpy()
    invalid = ~np.isfinite(wips)
    if config.WIPS_VALID_MIN is not None:
        invalid |= wips < config.WIPS_VALID_MIN
    if config.WIPS_VALID_MAX is not None:
        invalid |= wips > config.WIPS_VALID_MAX
    n_invalid = int((invalid & ~np.isnan(wips)).sum())
    if n_invalid:
        log.info("WIPS の異常値 %d 件を欠損として扱いました", n_invalid)
    df.loc[invalid, "wips"] = np.nan

    df["road_surface"] = df["road_surface"].astype("string").str.strip().str.lower()
    df.loc[df["road_surface"] == "", "road_surface"] = pd.NA
    bus = df["image_path"].astype("string").str.extract(IMAGE_RE)["bus"]
    df["bus"] = bus.fillna("unknown")
    if config.WIPS_EXCLUDED_BUSES:
        df.loc[df["bus"].isin(config.WIPS_EXCLUDED_BUSES), "wips"] = np.nan

    if bad_time.any() or bad_pos.any():
        log.info("時刻または位置が不正な観測 %d 件を除外しました", int(bad_time.sum() + bad_pos.sum()))
    return df.sort_values(["get_at", "obs_id"]).reset_index(drop=True)


def load_observations(start, end, db_path=config.DB_PATH):
    """期間 [start, end] の観測を返す（時刻順、クレンジング済み）。"""
    query = """
        SELECT id AS obs_id, latitude, longitude, get_at, WIPS AS wips, road_surface, image_path
        FROM pointed_road_data
        WHERE get_at >= ? AND get_at <= ?
        ORDER BY get_at, id
    """
    with closing(connect(db_path)) as conn:
        df = pd.read_sql_query(
            query, conn,
            params=(start.strftime(config.TIME_FORMAT), end.strftime(config.TIME_FORMAT)),
        )
    return clean_observations(df)
