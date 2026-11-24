import gzip
import logging

from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from services.status_service import BusyError, StatusService, ValidationError, parse_time

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
app.json.ensure_ascii = False


class PrefixMiddleware:
    """Apache の公開パス（例: /WinterRoad-Overview-LineStyle）を SCRIPT_NAME に設定する。

    Apache は ProxyPass でプレフィックスを外して転送してくるため、アプリ側で補う。
    プレフィックス付きで直接アクセスされた場合も PATH_INFO から取り除いて受け付ける。
    """

    def __init__(self, wsgi_app, prefix=""):
        self.app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if self.prefix:
            path = environ.get("PATH_INFO", "")
            if path == self.prefix or path.startswith(self.prefix + "/"):
                environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            environ["SCRIPT_NAME"] = self.prefix
        return self.app(environ, start_response)


app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=config.APP_PREFIX)

log.info("道路データを準備中...")
service = StatusService()
log.info("準備完了（%d 区間）", len(service.roads))


def _time_arg(name):
    v = request.args.get(name)
    return parse_time(v, name) if v else None


@app.errorhandler(ValidationError)
def handle_validation(e):
    return jsonify({"error": str(e)}), 400


@app.errorhandler(BusyError)
def handle_busy(e):
    return jsonify({"error": str(e)}), 503


@app.after_request
def compress(resp):
    """JSON を gzip 圧縮する（1KB 未満・圧縮済みは対象外）。"""
    if (resp.mimetype == "application/json" and not resp.direct_passthrough
            and "gzip" in request.headers.get("Accept-Encoding", "")
            and "Content-Encoding" not in resp.headers):
        data = resp.get_data()
        if len(data) >= 1024:
            resp.set_data(gzip.compress(data, compresslevel=5))
            resp.headers["Content-Encoding"] = "gzip"
            resp.headers["Vary"] = "Accept-Encoding"
    return resp


@app.route("/")
def index():
    return render_template(
        "index.html",
        geometry_version=service.signature,
        max_search_days=config.MAX_SEARCH_DAYS,
        thresholds={"danger": config.WIPS_DANGER_MAX, "warn": config.WIPS_WARN_MAX},
    )


@app.route("/api/roads/geometry")
def roads_geometry():
    """道路ジオメトリ（全区間）。内容は道路データが変わらない限り不変なので長期キャッシュ可。"""
    if "gzip" in request.headers.get("Accept-Encoding", ""):
        resp = send_file(service.geometry_path, mimetype="application/geo+json",
                         conditional=True, etag=service.signature, max_age=86400)
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers["Vary"] = "Accept-Encoding"
        return resp
    with gzip.open(service.geometry_path, "rb") as f:
        return Response(f.read(), mimetype="application/geo+json")


@app.route("/api/roads/status")
def roads_status():
    """区間ごとの代表点。

    パラメータ（すべて任意, 形式 YYYY-MM-DD HH:MM:SS）:
      base_start, base_end: 過去検索の期間。省略時は直近24時間（現在モード）
      start, end: base の中で代表点を選ぶ範囲（時間スライダー）
    """
    return jsonify(service.status(
        request.script_root,
        base_start=_time_arg("base_start"), base_end=_time_arg("base_end"),
        start=_time_arg("start"), end=_time_arg("end"),
    ))


@app.route("/api/roads/<int:seg_id>/timeline")
def road_timeline(seg_id):
    if seg_id < 0 or seg_id >= len(service.roads):
        return jsonify({"error": "区間が見つかりません"}), 404
    return jsonify({
        "seg_id": seg_id,
        "observations": service.timeline(
            seg_id,
            base_start=_time_arg("base_start"), base_end=_time_arg("base_end"),
            start=_time_arg("start"), end=_time_arg("end"),
        ),
    })


@app.route("/healthz")
def healthz():
    h = service.health()
    return jsonify(h), (200 if h["status"] == "ok" else 503)


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
