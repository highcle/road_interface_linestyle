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
    assert d["features"][0]["properties"]["label"] == "国道（幅員13〜19.5m）"
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
