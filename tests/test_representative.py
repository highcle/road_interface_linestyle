import math
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from services import representative as rp
from services.db_connector import clean_observations, load_observations


def obs(seg, t, wips, bus="A", surface="dry", obs_id=None):
    return {"obs_id": obs_id, "seg_id": seg, "get_at": pd.Timestamp(t), "wips": wips,
            "road_surface": surface, "image_path": f"img_{t}.jpg", "bus": bus, "dist_m": 5.0}


def frame(rows):
    df = pd.DataFrame(rows)
    df["obs_id"] = range(1, len(df) + 1)
    return df


START, END = datetime(2026, 1, 10, 0, 0), datetime(2026, 1, 10, 12, 0)


def test_latest_pass_wins_over_older_worse_pass():
    df = frame([
        obs(0, "2026-01-10 08:00:00", 3.0, surface="ice"),
        obs(0, "2026-01-10 11:00:00", 9.0),
        obs(0, "2026-01-10 11:00:20", 8.5, surface="wet"),
    ])
    rep = rp.select_representatives(df, START, END)[0]
    assert rep["wips"] == 8.5
    assert rep["road_surface"] == "wet"          # WIPS と同じ観測の路面状態
    assert rep["observed_at"] == "2026-01-10 11:00:20"
    assert rep["pass"]["n_obs"] == 2
    assert rep["stats"] == {
        "n_obs": 3, "n_passes": 2, "wips_min": 3.0, "wips_median": 8.5, "wips_max": 9.0,
        "first_at": "2026-01-10 08:00:00", "last_at": "2026-01-10 11:00:20",
    }


def test_pass_split_by_gap_and_vehicle():
    df = frame([
        obs(0, "2026-01-10 10:00:00", 8.0),
        obs(0, "2026-01-10 10:09:00", 8.1),   # 9分差 → 同じ通過
        obs(0, "2026-01-10 10:30:00", 9.0),   # 21分差 → 別の通過
        obs(0, "2026-01-10 10:30:00", 9.9, bus="B"),  # 別車両 → 別の通過
    ])
    passes = rp.assign_passes(df)
    assert passes.groupby("pass_key").size().sort_values().tolist() == [1, 1, 2]


def test_simultaneous_passes_choose_worse():
    df = frame([
        obs(1, "2026-01-10 10:00:00", 9.1, bus="B"),
        obs(1, "2026-01-10 10:00:00", 7.0, bus="C", surface="slush"),
    ])
    rep = rp.select_representatives(df, START, END)[1]
    assert (rep["bus"], rep["wips"], rep["road_surface"]) == ("C", 7.0, "slush")


def test_tie_within_pass_prefers_newer():
    df = frame([
        obs(0, "2026-01-10 10:00:00", 8.0, surface="dry"),
        obs(0, "2026-01-10 10:00:10", 8.0, surface="wet"),
    ])
    rep = rp.select_representatives(df, START, END)[0]
    assert rep["observed_at"] == "2026-01-10 10:00:10"


def test_pass_without_valid_wips_uses_latest_observation():
    df = frame([
        obs(2, "2026-01-10 09:00:00", 9.0),
        obs(2, "2026-01-10 11:30:00", np.nan, surface="fresh"),
        obs(2, "2026-01-10 11:30:10", np.nan, surface="ice"),
    ])
    rep = rp.select_representatives(df, START, END)[2]
    assert rep["wips"] is None
    assert rep["road_surface"] == "ice"
    assert rep["observed_at"] == "2026-01-10 11:30:10"


def test_window_limits_observations():
    df = frame([
        obs(0, "2026-01-10 08:00:00", 3.0),
        obs(0, "2026-01-10 11:00:00", 9.0),
    ])
    rep = rp.select_representatives(df, datetime(2026, 1, 10, 7), datetime(2026, 1, 10, 9))[0]
    assert rep["wips"] == 3.0
    assert rp.select_representatives(df, datetime(2026, 1, 10, 12, 1), datetime(2026, 1, 10, 13)) == {}


def test_age_minutes_relative_to_window_end():
    df = frame([obs(0, "2026-01-10 11:00:00", 9.0)])
    assert rp.select_representatives(df, START, END)[0]["age_minutes"] == 60


def test_empty_input():
    assert rp.select_representatives(frame([obs(0, "2026-01-10 11:00:00", 9.0)]).iloc[0:0], START, END) == {}


# ---- クレンジング ----------------------------------------------------------
def test_clean_observations_handles_invalid_values():
    raw = pd.DataFrame({
        "obs_id": [1, 2, 3, 4],
        "latitude": [43.0, 43.0, 0, 43.0],
        "longitude": [141.3, 141.3, 141.3, 141.3],
        "get_at": ["2026-01-10 10:00:00", "2026-01-10 10:01:00", "2026-01-10 10:02:00", "bad"],
        "wips": [-math.inf, 8.0, 8.0, 8.0],
        "road_surface": [" ICE ", "dry", "dry", "dry"],
        "image_path": ["image_100126_100000_1_bus_beta.jpg", "x.jpg", None, None],
    })
    df = clean_observations(raw)
    assert df["obs_id"].tolist() == [1, 2]          # 位置0・不正時刻は除外
    assert np.isnan(df.loc[0, "wips"])              # -Inf は欠損扱い
    assert df.loc[0, "road_surface"] == "ice"       # 路面状態は残す（正規化）
    assert df["bus"].tolist() == ["beta", "unknown"]


def test_load_observations_from_db_is_sorted_and_clean():
    df = load_observations(datetime(2026, 1, 9, 12), datetime(2026, 1, 10, 12))
    assert df["get_at"].is_monotonic_increasing
    assert not np.isinf(df["wips"].to_numpy(dtype=float)).any()
    assert len(df) == 11  # 不正時刻1件と範囲外1件を除く


@pytest.mark.parametrize("name,expected", [
    ("image_260126_064717_2_bus_beta.jpg", ("260126", "beta")),
    ("image_200126_054812_1_bus_A.jpg", ("200126", "A")),
    ("image_200126_054812_12_bus_K.jpg", ("200126", "K")),
    ("broken.jpg", None),
])
def test_parse_image_name(name, expected):
    from services.db_connector import parse_image_name
    info = parse_image_name(name)
    assert (info and (info["date"], info["bus"])) == expected if expected else info is None
