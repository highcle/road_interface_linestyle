"""区間ごとの代表点（代表観測）の選出。

採用アルゴリズム: 「最新通過内の最小WIPS観測（Latest-Pass Minimum WIPS）」

1. 区間ごとに、同一車両の観測を時刻順に並べ、間隔が PASS_GAP_MINUTES を超えたら
   別の「通過（pass）」とする。1回の通過は、ほぼ同一時刻・同一車両・同一カメラによる
   同じ道路区間の観測なので、気象・路面条件は共通とみなせる。
2. 区間内の通過のうち、最も新しい（終了時刻が最も遅い）通過を選ぶ。
   → 古い通過の情報は現在の状態を表さないため使わない（鮮度の確保）。
   同時刻に複数車両が通過した場合は、最小WIPSが低い方（より悪い方）を選ぶ。
3. その通過の観測のうち、WIPS が最小の観測を代表点とする。同値なら新しい方。
   → 通過内の差はカメラの揺れ・対向車・遮蔽物などの短時間変動であり、
     安全側（視程が悪い側）を採る。上流の WIPS 算出処理が10フレーム中の最小値を
     採用し、その画像で路面状態を判別している考え方とも整合する。
   通過内に有効な WIPS が1つもなければ、その通過の最新観測を代表点とする（WIPS は欠損）。

代表点は「実在する1つの観測」なので、WIPS・路面状態・時刻・画像が必ず同じ観測に
由来し、画像を見れば表示値の根拠を確認できる。
期間内の全観測の統計（件数、通過回数、WIPS 最小/中央値/最大）は参考情報として別に返す。
"""
from datetime import datetime

import numpy as np
import pandas as pd

import config

ALGORITHM = {
    "id": "latest_pass_min_wips",
    "name": "最新通過内の最小WIPS観測",
    "description": "区間を最後に通過した車両の観測のうち、WIPSが最も低い（視程が悪い）観測を代表点とする",
}


def assign_passes(matched, gap_minutes=config.PASS_GAP_MINUTES):
    """matched に pass_no（区間内で通し番号）列を付けて返す。"""
    if len(matched) == 0:
        return matched.assign(pass_no=pd.Series(dtype=int))
    df = matched.sort_values(["seg_id", "bus", "get_at", "obs_id"]).reset_index(drop=True)
    gap = pd.Timedelta(minutes=gap_minutes)
    new_pass = (
        (df["seg_id"] != df["seg_id"].shift())
        | (df["bus"] != df["bus"].shift())
        | ((df["get_at"] - df["get_at"].shift()) > gap)
    )
    df["pass_key"] = new_pass.cumsum()
    # 区間内で時系列順の通し番号（1始まり）
    first_t = df.groupby("pass_key")["get_at"].transform("min")
    df["pass_no"] = (df.assign(_t=first_t)
                       .groupby("seg_id")["_t"].rank(method="dense").astype(int))
    return df


def _fmt(t):
    return None if pd.isna(t) else pd.Timestamp(t).strftime(config.TIME_FORMAT)


def _num(x, nd=3):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def select_representatives(matched, start, end, gap_minutes=config.PASS_GAP_MINUTES):
    """期間 [start, end] の観測から区間ごとの代表点を選ぶ。

    Returns:
        {seg_id(int): {...}} 代表点と期間内統計
    """
    if len(matched) == 0:
        return {}
    win = matched[(matched["get_at"] >= pd.Timestamp(start)) & (matched["get_at"] <= pd.Timestamp(end))]
    if len(win) == 0:
        return {}
    df = assign_passes(win, gap_minutes)

    # --- 通過ごとの要約
    passes = df.groupby("pass_key").agg(
        seg_id=("seg_id", "first"),
        bus=("bus", "first"),
        t_start=("get_at", "min"),
        t_end=("get_at", "max"),
        n=("obs_id", "size"),
        wmin=("wips", "min"),
    )
    passes["wmin_sort"] = passes["wmin"].fillna(np.inf)
    # 区間ごとに最新の通過（同時刻なら WIPS の低い方）
    latest = (passes.sort_values(["seg_id", "t_end", "wmin_sort"], ascending=[True, False, True])
                    .groupby("seg_id").head(1))

    # --- 最新通過内の代表観測: WIPS 最小（欠損は最後）、同値なら新しい方
    cand = df[df["pass_key"].isin(latest.index)].copy()
    cand["wips_sort"] = cand["wips"].fillna(np.inf)
    rep = (cand.sort_values(["pass_key", "wips_sort", "get_at"], ascending=[True, True, False])
               .groupby("pass_key").head(1)
               .set_index("seg_id"))

    # --- 期間内の統計
    stats = df.groupby("seg_id").agg(
        n_obs=("obs_id", "size"),
        n_passes=("pass_key", "nunique"),
        wips_min=("wips", "min"),
        wips_median=("wips", "median"),
        wips_max=("wips", "max"),
        first_at=("get_at", "min"),
        last_at=("get_at", "max"),
    )

    end_ts = pd.Timestamp(end)
    latest_by_seg = latest.set_index("seg_id")
    out = {}
    for seg_id, r in rep.iterrows():
        p = latest_by_seg.loc[seg_id]
        s = stats.loc[seg_id]
        surface = r["road_surface"]
        out[int(seg_id)] = {
            "wips": _num(r["wips"]),
            "road_surface": None if pd.isna(surface) else str(surface),
            "observed_at": _fmt(r["get_at"]),
            "age_minutes": int((end_ts - r["get_at"]).total_seconds() // 60),
            "obs_id": int(r["obs_id"]),
            "image_path": None if pd.isna(r["image_path"]) else str(r["image_path"]),
            "bus": str(r["bus"]),
            "pass": {
                "start": _fmt(p["t_start"]),
                "end": _fmt(p["t_end"]),
                "n_obs": int(p["n"]),
            },
            "stats": {
                "n_obs": int(s["n_obs"]),
                "n_passes": int(s["n_passes"]),
                "wips_min": _num(s["wips_min"]),
                "wips_median": _num(s["wips_median"]),
                "wips_max": _num(s["wips_max"]),
                "first_at": _fmt(s["first_at"]),
                "last_at": _fmt(s["last_at"]),
            },
        }
    return out


def segment_timeline(matched, seg_id, start, end, gap_minutes=config.PASS_GAP_MINUTES):
    """1区間の期間内観測を通過番号付きで返す（詳細パネルの時系列表示用）。"""
    sub = matched[(matched["seg_id"] == seg_id)
                  & (matched["get_at"] >= pd.Timestamp(start))
                  & (matched["get_at"] <= pd.Timestamp(end))]
    df = assign_passes(sub, gap_minutes).sort_values(["get_at", "obs_id"])
    return [
        {
            "t": _fmt(r.get_at),
            "wips": _num(r.wips),
            "road_surface": None if pd.isna(r.road_surface) else str(r.road_surface),
            "bus": str(r.bus),
            "pass_no": int(r.pass_no),
            "obs_id": int(r.obs_id),
        }
        for r in df.itertuples()
    ]


def to_datetime(s):
    return datetime.strptime(s, config.TIME_FORMAT)
