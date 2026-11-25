import pandas as pd

from services.bus_service import select_bus_positions


def obs(i, t, lat, lon, bus, wips=9.0):
    return {"obs_id": i, "get_at": pd.Timestamp(t), "latitude": lat, "longitude": lon,
            "wips": wips, "road_surface": "dry", "image_path": f"img{i}.jpg", "bus": bus}


def test_latest_point_per_bus_with_heading():
    df = pd.DataFrame([
        obs(1, "2026-01-10 11:56:00", 43.000, 141.300, "A"),
        obs(2, "2026-01-10 11:57:00", 43.002, 141.300, "A"),   # 北へ約220m
        obs(3, "2026-01-10 11:58:00", 43.004, 141.300, "A"),
    ])
    (b,) = select_bus_positions(df)
    assert b["obs_id"] == 3 and b["bus"] == "A"
    assert b["heading"] in (0.0, 360.0)   # 真北向き
    assert b["merged"] == []


def test_nearby_points_merge_into_latest():
    df = pd.DataFrame([
        obs(1, "2026-01-10 11:57:00", 43.0000, 141.3000, "A"),
        obs(2, "2026-01-10 11:58:00", 43.0003, 141.3003, "B"),   # A から約40m
        obs(3, "2026-01-10 11:58:30", 43.1000, 141.3000, "C"),   # 遠い
    ])
    buses = {b["bus"]: b for b in select_bus_positions(df)}
    assert set(buses) == {"B", "C"}
    assert buses["B"]["merged"] == ["A"]


def test_unknown_bus_points_are_merged_by_distance():
    df = pd.DataFrame([
        obs(1, "2026-01-10 11:57:00", 43.0000, 141.3000, "unknown"),
        obs(2, "2026-01-10 11:58:00", 43.0002, 141.3000, "unknown"),  # 約22m
        obs(3, "2026-01-10 11:59:00", 43.0500, 141.3000, "unknown"),  # 遠い
    ])
    assert sorted(b["obs_id"] for b in select_bus_positions(df)) == [2, 3]


def test_empty():
    assert select_bus_positions(pd.DataFrame(columns=["obs_id"])) == []


def test_buses_api(client):
    r = client.get("/api/buses")
    assert r.status_code == 200
    d = r.get_json()
    assert d["now"] == "2026-01-10 12:00:00" and d["window_minutes"] == 5
    (g,) = d["buses"]                                  # H は5分より前なので出ない
    assert g["bus"] == "G" and g["merged"] == ["F"]   # F の最新点は G から約20m
    assert g["age_seconds"] == 60
    assert g["image_url"].endswith("/static/images/_indicated_bus_G/100126/image_100126_115900_1_bus_G.jpg")
