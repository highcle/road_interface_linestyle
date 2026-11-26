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
    # 一覧で強調するのは「どこで」（路線・市町村）。状態は補足の行に出す
    assert items.first.locator(".alert-place").inner_text() == "都道府県道"   # 路線名なし・幅員は出さない
    assert "視程不良（WIPS 7.00）" in items.first.locator(".alert-sub").first.inner_text()
    items.first.click()
    page.wait_for_selector("#detailPanel:not([hidden])")
    kpis = page.inner_text("#detailBody .kpis")
    assert "7.00" in kpis and "シャーベット" in kpis
    body = page.inner_text("#detailBody")
    # 詳細は状態・観測時刻・画像だけ（車両番号・代表点の説明・期間の集計・推移グラフ・区間ID・幅員は出さない）
    for gone in ("観測車両", "代表点", "回通過", "区間ID", "幅員"):
        assert gone not in body
    assert "幅員" not in page.inner_text("#detailPanel")
    assert page.locator("#detailBody svg").count() == 0
    assert "seg=1" in page.evaluate("location.hash")


def test_surface_indicator_and_filter(page):
    page.click("[data-indicator=surface]")
    assert page.get_attribute("[data-indicator=surface]", "aria-pressed") == "true"
    legend = page.inner_text("#legendArea")
    assert "湿潤" in legend and "積雪（新雪）" in legend
    assert page.text_content("#alertCount") == "2 件"     # seg1: slush, seg2: fresh（路線が別）
    page.locator(".legend-item", has_text="積雪（新雪）").locator("input").uncheck()
    assert page.text_content("#alertCount") == "1 件"
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


def test_bus_marker(page):
    # 12:00 の5分以内: G（F は G から約20m のためまとめられる）
    page.wait_for_selector(".bus-marker")
    assert page.locator(".bus-marker").count() == 1
    page.hover(".bus-marker")
    tip = page.text_content(".bus-tooltip")
    # 車両番号は表示しない。まとめた台数だけ示す
    assert "G" not in tip and "F" not in tip and "車両" not in tip
    assert "近くにいる他の 1 台" in tip
    # 過去データの表示中はバスを出さない
    page.click("#btnModeHistory")
    page.click("#historyDialog [data-preset='yesterday']")
    page.click("#btnHistorySearch")
    page.wait_for_function("document.querySelector('#historyBanner').hidden === false")
    page.wait_for_function("document.querySelectorAll('.bus-marker').length === 0")


def _js(page, body):
    return page.evaluate(f"""async () => {{
        const m = await import('{PREFIX}/static/js/roadmap.js');
        const c = await import('{PREFIX}/static/js/categories.js');
        const a = await import('{PREFIX}/static/js/alerts.js');
        const st = (await import('{PREFIX}/static/js/state.js')).state;
        {body}
    }}""")


def test_map_click_selects_one_after_another(page):
    """地図上の線を続けてクリックしても、毎回その区間が選ばれる（強調表示がクリックを奪わない）"""
    page.click("#timeBar [data-hours='all']")
    page.wait_for_function("document.querySelector('#status').textContent.startsWith('3 区間')")
    _js(page, "m.map.fitBounds(L.latLngBounds([[42.999, 141.299], [43.011, 141.331]]), { paddingTopLeft: [80, 200], paddingBottomRight: [480, 80] }); "
              "await new Promise((r) => setTimeout(r, 600));")
    for seg in (0, 2, 1, 0):
        x, y = _js(page, f"""const p = m.map.latLngToContainerPoint(m.centerOf({seg}));
            const r = m.map.getContainer().getBoundingClientRect(); return [p.x + r.left, p.y + r.top];""")
        page.mouse.click(x, y)
        page.wait_for_function(f"location.hash.includes('seg={seg}')")
        assert page.is_visible("#detailPanel")


def test_lines_use_class_colors(page):
    """線の色は区分の色だけ（凡例にない色は使わない）。表示切り替えのチェックボックスは置かない"""
    assert _js(page, "return m.getLayer(0).options.color;") == "#1f6fb2"     # seg0: WIPS 9.0 → 良好
    legend = _js(page, "return c.INDICATORS.wips.classes.map((k) => k.color);")
    for seg in (0, 1):
        assert _js(page, f"return m.getLayer({seg}).options.color;") in legend
    assert page.locator("#optGradient, #optBuses").count() == 0


def test_group_alerts(page):
    """注意区間は「路線 × 市町村」で1件にまとめ、最も悪い区間の値を示す"""
    groups = _js(page, """
        const cls = c.INDICATORS.wips.classes;
        const danger = cls.find((k) => k.key === 'wips_danger'), warn = cls.find((k) => k.key === 'wips_warn');
        const it = (id, wips, k, t) => ({ id, cls: k, rep: { wips, observed_at: t, age_minutes: 5 } });
        // 1・2・3 は国道5号・札幌市（3 は重複区間「国道5号・230号」）/ 4 は道道1号 / 5 は国道5号の小樽市
        const items = [it(1, 7.8, warn, '2026-01-10 11:00:00'), it(2, 7.1, danger, '2026-01-10 11:01:00'),
                       it(3, 7.7, warn, '2026-01-10 11:02:00'), it(4, 6.0, danger, '2026-01-10 10:00:00'),
                       it(5, 7.9, warn, '2026-01-10 09:00:00')];
        const route = { 1: '国道5号', 2: '国道5号', 3: '国道5号・230号', 4: '道道1号 テスト線', 5: '国道5号' };
        const muni = { 1: '札幌市', 2: '札幌市', 3: '札幌市', 4: '札幌市', 5: '小樽市' };
        const gs = a.groupAlerts(items, { routeOf: (i) => route[i], muniOf: (i) => muni[i], lengthOf: () => 100 });
        return gs.map((g) => ({ key: `${g.route} ${g.muni}`, ids: [...g.ids].sort(), worst: g.worst.id,
                                len: g.length, latest: g.latest }));
    """)
    assert groups == [
        {"key": "道道1号 テスト線 札幌市", "ids": [4], "worst": 4, "len": 100, "latest": "2026-01-10 10:00:00"},
        {"key": "国道5号 札幌市", "ids": [1, 2, 3], "worst": 2, "len": 300, "latest": "2026-01-10 11:02:00"},
        {"key": "国道5号 小樽市", "ids": [5], "worst": 5, "len": 100, "latest": "2026-01-10 09:00:00"},
    ]
