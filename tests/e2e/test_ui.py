"""ブラウザ操作による E2E テスト（Playwright + Chrome/Chromium）。

実行: python -m pytest tests/e2e  （playwright 未導入なら自動でスキップ）
初回のみ `playwright install chromium` が必要（システムの Google Chrome があれば不要）。
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREFIX = "/WinterRoad-Overview-LineStyle"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    env = dict(os.environ, APP_PORT=str(port), APP_HOST="127.0.0.1")
    subprocess.run([sys.executable, "generate_cache.py"], cwd=ROOT, env=env, check=True, capture_output=True)
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{base}/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    yield f"{base}{PREFIX}/"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            try:
                b = p.chromium.launch(headless=True)
            except Exception as e:  # ブラウザ未導入
                pytest.skip(f"ブラウザを起動できません: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser, server):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(server, wait_until="networkidle")
    pg.wait_for_function("document.querySelector('#status').textContent.includes('区間に観測あり')")
    yield pg
    assert errors == [], errors
    pg.close()


def test_initial_live_view(page):
    assert page.text_content("#timeModeLabel") == "直近24時間"
    # 既定は直近6時間: 06:00〜12:00 → seg0, seg1, seg2
    assert "1/10 06:00 〜 12:00" in page.text_content("#timeRangeLabel")
    assert page.text_content("#status").startswith("3 区間")
    # 1時間にすると seg0(11:00), seg2(11:30) のみ
    page.click("#timeBar [data-hours='1']")
    page.wait_for_function("document.querySelector('#status').textContent.startsWith('2 区間')")
    assert "データ更新 12:00" in page.text_content("#freshness")


def test_select_from_alert_list_shows_coherent_detail(page):
    page.click("#timeBar [data-hours='all']")
    page.wait_for_function("document.querySelector('#status').textContent.startsWith('3 区間')")
    items = page.locator("#alertList .alert-item")
    assert items.count() == 1                     # seg1: WIPS 7.0（視程不良）
    items.first.click()
    page.wait_for_selector("#detailPanel:not([hidden])")
    kpis = page.inner_text("#detailBody .kpis")
    assert "7.00" in kpis and "シャーベット" in kpis
    assert "観測車両\nC" in page.inner_text("#detailBody .facts").replace("\t", "\n")
    page.wait_for_selector("#timelineChart svg .rep-mark")
    assert "seg=1" in page.evaluate("location.hash")


def test_surface_indicator_and_filter(page):
    page.click("[data-indicator=surface]")
    assert page.get_attribute("[data-indicator=surface]", "aria-pressed") == "true"
    legend = page.inner_text("#legendArea")
    assert "湿潤" in legend and "積雪（新雪）" in legend
    assert page.text_content("#alertCount") == "2"     # seg1: slush, seg2: fresh
    page.locator(".legend-item", has_text="積雪（新雪）").locator("input").uncheck()
    assert page.text_content("#alertCount") == "1"
    page.locator(".legend-item", has_text="シャーベット").locator("input").uncheck()
    assert "表示範囲内に該当する区間はありません" in page.text_content("#alertList")
    # 設定はリロード後も保持される
    page.reload(wait_until="networkidle")
    page.wait_for_function("document.querySelector('#status').textContent.includes('区間')")
    assert page.get_attribute("[data-indicator=surface]", "aria-pressed") == "true"
    assert not page.locator(".legend-item", has_text="積雪（新雪）").locator("input").is_checked()
    page.evaluate("localStorage.clear()")


def test_filter_hides_segment_on_map(page):
    """凡例のチェックを外した区分の線は地図上で非表示・クリック不可になる（課題1-3）"""
    def style_of(seg):
        return page.evaluate(f"""async () => {{
            const m = await import('{PREFIX}/static/js/roadmap.js');
            const o = m.getLayer({seg}).options; return [o.opacity, o.interactive];
        }}""")
    assert style_of(1)[0] > 0
    page.locator(".legend-item", has_text="視程不良").locator("input").uncheck()
    assert style_of(1) == [0, False]
    page.locator(".legend-item", has_text="視程不良").locator("input").check()
    page.evaluate("localStorage.clear()")


def test_history_search_validation_and_back_to_live(page):
    page.click("#btnModeHistory")
    page.fill("#historyStart", "2026-01-09T00:00")
    page.fill("#historyEnd", "2026-01-08T00:00")
    assert "前にしてください" in page.text_content("#historyError")
    assert page.is_disabled("#btnHistorySearch")
    page.fill("#historyStart", "2026-01-08T00:00")
    page.fill("#historyEnd", "2026-01-09T00:00")
    page.click("#btnHistorySearch")
    page.wait_for_selector("#historyBanner:not([hidden])")
    page.wait_for_function("document.querySelector('#timeModeLabel').textContent === '検索期間'")
    page.click("#timeBar [data-hours='all']")
    page.wait_for_function("document.querySelector('#status').textContent.startsWith('1 区間')")
    assert "hist=" in page.evaluate("location.hash")
    page.click("#btnBackToLive")
    page.wait_for_function("document.querySelector('#timeModeLabel').textContent === '直近24時間'")
    assert page.locator("#historyBanner").is_hidden()


def test_url_restores_history_view(browser, server, page):
    page.click("#btnModeHistory")
    page.fill("#historyStart", "2026-01-08T00:00")
    page.fill("#historyEnd", "2026-01-09T00:00")
    page.click("#btnHistorySearch")
    page.wait_for_function("location.hash.includes('hist=')")
    url = server + page.evaluate("location.hash")
    other = browser.new_page()
    other.goto(url, wait_until="networkidle")
    other.wait_for_function("document.querySelector('#timeModeLabel').textContent === '検索期間'")
    assert "1/8" in other.text_content("#historyBannerText")
    other.close()


def test_mobile_layout(browser, server):
    m = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    m.goto(server, wait_until="networkidle")
    assert m.get_attribute("#btnPanelToggle", "aria-expanded") == "false"   # 地図を優先
    m.click("#btnPanelToggle")
    assert m.is_visible("#legendArea")
    m.close()


def test_help_dialog_closes_with_escape(page):
    page.click("#btnHelp")
    assert page.is_visible("#helpDialog")
    assert "Weighted Intensity of Power Spectra" in page.text_content("#helpDialog")
    page.keyboard.press("Escape")
    assert not page.is_visible("#helpDialog")


def test_failed_history_search_reverts_to_live(page):
    """過去検索が失敗（混雑 503）したら、現在表示のまま操作を続けられる"""
    page.route("**/api/roads/status?base_start=*", lambda route: route.fulfill(
        status=503, content_type="application/json",
        body='{"error": "他の検索を処理中です。しばらくしてから再度お試しください"}'))
    page.click("#btnModeHistory")
    page.fill("#historyStart", "2026-01-08T00:00")
    page.fill("#historyEnd", "2026-01-09T00:00")
    page.click("#btnHistorySearch")
    page.wait_for_function("document.querySelector('#status').textContent.includes('他の検索を処理中')")
    assert page.text_content("#timeModeLabel") == "直近24時間"
    assert page.locator("#historyBanner").is_hidden()
    assert "〜" in page.text_content("#timeRangeLabel")
    # スライダー操作で通常どおり更新できる
    page.click("#timeBar [data-hours='1']")
    page.wait_for_function("document.querySelector('#status').textContent.startsWith('2 区間')")
