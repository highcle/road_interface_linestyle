import gzip
import json
import os

import pytest

import generate_cache

PREFIX = "/WinterRoad-Overview-LineStyle"


@pytest.fixture(scope="module")
def client():
    generate_cache.main()
    import app as app_module
    return app_module.app.test_client()


def get_json(client, url):
    r = client.get(url)
    return r, json.loads(r.data)


def test_index_with_and_without_prefix(client):
    for url in ["/", f"{PREFIX}/"]:
        r = client.get(url)
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert f'href="{PREFIX}/static/css/style.css' in html
        assert 'name="viewport"' in html
    # 静的ファイルはプレフィックスの有無どちらでも取得できる（ローカル直接アクセス対応）
    assert client.get("/static/js/main.js").status_code == 200
    assert client.get(f"{PREFIX}/static/js/main.js").status_code == 200


def test_status_live(client):
    r, d = get_json(client, "/api/roads/status")
    assert r.status_code == 200
    assert d["mode"] == "live"
    assert d["window"] == {"start": "2026-01-09 12:00:00", "end": "2026-01-10 12:00:00"}
    segs = d["segments"]
    assert set(segs) == {"0", "1", "2"}  # 対象外道路・50m 超の観測は紐付かない
    assert segs["0"]["wips"] == 8.2 and segs["0"]["road_surface"] == "wet"
    assert segs["0"]["image_url"] == f"{PREFIX}/static/images/_indicated_bus_A/100126/image_100126_110015_1_bus_A.jpg"
    assert segs["1"]["bus"] == "C"
    assert segs["2"]["wips"] is None and segs["2"]["road_surface"] == "fresh"
    assert d["cache_stale"] is False
    assert "Infinity" not in r.get_data(as_text=True) and "NaN" not in r.get_data(as_text=True)


def test_status_sub_range(client):
    _, d = get_json(client, "/api/roads/status?start=2026-01-10 07:00:00&end=2026-01-10 09:00:00")
    assert d["range"] == {"start": "2026-01-10 07:00:00", "end": "2026-01-10 09:00:00"}
    assert d["segments"]["0"]["wips"] == 5.0
    assert set(d["segments"]) == {"0", "2"}


def test_status_history_and_cache(client):
    url = "/api/roads/status?base_start=2026-01-08 00:00:00&base_end=2026-01-09 00:00:00"
    r, d = get_json(client, url)
    assert r.status_code == 200 and d["mode"] == "history"
    assert d["segments"]["0"]["wips"] == 2.0


@pytest.mark.parametrize("query,msg", [
    ("base_start=2026-01-10 00:00:00&base_end=2026-01-09 00:00:00", "開始日時は終了日時より前"),
    ("base_start=2025-12-01 00:00:00&base_end=2026-01-09 00:00:00", "最大 7 日"),
    ("base_start=2026-01-09 00:00:00", "両方指定"),
    ("base_start=abc&base_end=def", "形式が不正"),
    ("base_start=2026-02-01 00:00:00&base_end=2026-02-02 00:00:00", "未来"),
    ("start=2026-01-10 11:00:00&end=2026-01-10 10:00:00", "表示範囲"),
])
def test_status_validation(client, query, msg):
    r, d = get_json(client, f"/api/roads/status?{query}")
    assert r.status_code == 400
    assert msg in d["error"]


def test_geometry_gzip_and_etag(client):
    r = client.get("/api/roads/geometry", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers["Content-Encoding"] == "gzip"
    d = json.loads(gzip.decompress(r.data))
    assert [f["properties"]["id"] for f in d["features"]] == [0, 1, 2]
    assert d["features"][0]["properties"]["kind"] == "国道（幅員13〜19.5m）"
    etag = r.headers["ETag"]
    r2 = client.get("/api/roads/geometry", headers={"Accept-Encoding": "gzip", "If-None-Match": etag})
    assert r2.status_code == 304
    # gzip 非対応クライアント
    r3 = client.get("/api/roads/geometry")
    assert json.loads(r3.data)["type"] == "FeatureCollection"


def test_status_is_gzipped_when_accepted(client):
    r = client.get("/api/roads/status", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") == "gzip"
    assert json.loads(gzip.decompress(r.data))["mode"] == "live"


def test_timeline(client):
    r, d = get_json(client, "/api/roads/0/timeline")
    assert r.status_code == 200
    assert [o["pass_no"] for o in d["observations"]] == [1, 1, 2, 2, 2]
    assert client.get("/api/roads/999/timeline").status_code == 404


def test_healthz_reports_stale_cache(client, monkeypatch):
    import config
    r, d = get_json(client, "/healthz")
    assert r.status_code == 200 and d["status"] == "ok"
    monkeypatch.setattr(config, "FIXED_NOW", "2026-01-10 13:00:00")
    r, d = get_json(client, "/healthz")
    assert r.status_code == 503 and d["status"] == "stale"
    _, s = get_json(client, "/api/roads/status")
    assert s["cache_stale"] is True


def test_cache_files_written():
    import config
    names = os.listdir(config.CACHE_DIR)
    assert "recent_matched.pkl" in names
    assert any(n.startswith("geometry_") for n in names)


def test_range_outside_window_falls_back_to_whole_window(client):
    """時間が経って表示範囲が期間外になっても 400 にせず、期間全体を返す（自動更新が止まらない）"""
    r, d = get_json(client, "/api/roads/status?start=2026-01-08 08:00:00&end=2026-01-08 10:00:00")
    assert r.status_code == 200
    assert d["range"] == d["window"]


def test_geometry_has_route_and_municipality(client):
    r = client.get("/api/roads/geometry")
    props = {f["properties"]["id"]: f["properties"] for f in json.loads(r.data)["features"]}
    assert props[0]["label"] == "国道5号"
    assert props[0]["muni"] == "札幌市南区"
    assert props[0]["kind"] == "国道（幅員13〜19.5m）"
    # 位置が一致しない行は使わない → 道路分類で表示
    assert props[1]["label"] == props[1]["kind"] == "都道府県道（幅員5.5〜13m）"
    assert props[1]["muni"] == ""
    assert props[2]["muni"] == ""


LEGACY_KEYS = {f"N13_{i:03d}" for i in range(1, 9)} | {
    "display_route_name", "wips", "road_surface", "last_updated", "image_path"}


def test_legacy_recent(client):
    for headers in ({}, {"Accept-Encoding": "gzip"}):
        r = client.get("/api/roads/recent", headers=headers)
        assert r.status_code == 200
        body = gzip.decompress(r.data) if r.headers.get("Content-Encoding") == "gzip" else r.data
        data = json.loads(body)  # -Inf を含んでいても正しい JSON
        assert data["type"] == "FeatureCollection"
        f = {x["id"]: x for x in data["features"]}
        assert set(f) == {"0", "1", "2"}  # データのない区間も含む全区間
        p0 = f["0"]["properties"]
        assert set(p0) == LEGACY_KEYS
        assert p0["N13_003"] == "1" and p0["N13_005"] == 0
        assert p0["display_route_name"] == "国道5号"
        # 旧実装と同じ集計: WIPS は期間内の平均、他は最後の観測
        assert p0["wips"] == round((5.0 + 5.5 + 9.0 + 8.2 + 9.5) / 5, 2)
        assert p0["road_surface"] == "dry"
        assert p0["last_updated"] == "2026-01-10 11:00:30"
        assert p0["image_path"] == "image_100126_110030_1_bus_A.jpg"
        # 異常値(-Inf)は平均から除く
        assert f["2"]["properties"]["wips"] == 9.0
        assert f["2"]["properties"]["road_surface"] == "fresh"


def test_legacy_search(client):
    r, data = get_json(client, "/api/roads/search?start_time=2026-01-10 10:30:00&end_time=2026-01-10 12:00:00")
    assert r.status_code == 200
    f = {x["id"]: x["properties"] for x in data["features"]}
    assert f["0"]["wips"] == round((9.0 + 8.2 + 9.5) / 3, 2)
    assert f["1"]["wips"] is None and f["1"]["last_updated"] is None
    r, data = get_json(client, "/api/roads/search")
    assert r.status_code == 400
    r, data = get_json(client, "/api/roads/search?start_time=2026-01-01 00:00:00&end_time=2026-01-10 00:00:00")
    assert r.status_code == 400
