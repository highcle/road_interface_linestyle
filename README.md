# 冬季道路情報提供インターフェース（線的表示）

車両（バス）に搭載したセンサ・カメラで取得した **路面状態** と **WIPS 指標** を、北海道の主要道路網に紐付けて **線（道路区間）単位で色分け表示** する Web アプリケーションです。

- 直近24時間の状況を 5 分ごとに自動更新して表示
- 時間スライダーで直近24時間内の表示範囲を絞り込み
- カレンダーから任意の過去期間を検索
- 区間をクリックすると、WIPS 値・路面状態・最終観測時刻・路面画像を表示

> 本リポジトリ内の `database.db` はテストデータです。本番環境ではリアルタイムに観測データが送信され、データベースへ随時登録されます。

課題点の洗い出し結果は [`docs/issues_report.md`](docs/issues_report.md) を参照してください。

---

## システム構成

```
観測データ（車載センサ/カメラ）
        │  リアルタイム登録
        ▼
SQLite: database.db (pointed_road_data)
        │
        ├─ cron (5分毎): generate_cache.py
        │     直近24hを抽出 → 最寄り道路へ空間結合(50m以内) → 区間ごと集計
        │     → output_24h.json（アトミックに置換）
        │
        └─ Flask: app.py (127.0.0.1:5100)
              GET /                    画面
              GET /api/roads/recent    output_24h.json を返す
              GET /api/roads/search    指定期間をその場で検索・集計
                   ▲
                   │ リバースプロキシ (/WinterRoad-Overview-LineStyle)
                Apache
                   ▲
                ブラウザ（Leaflet + 国土地理院 淡色地図 + noUiSlider）
```

### 処理の流れ

1. **道路データ読み込み**（`services/road_loader.py`）
   `geojson/` 以下の国土数値情報 道路データ（N13）を読み込み、`N13_003` が対象種別（`config.TARGET_ROAD_TYPES`）の区間だけを抽出します。座標系は JGD2011（EPSG:6668）。
2. **観測データ取得**（`services/db_connector.py`）
   `pointed_road_data` から指定期間（`get_at`）の観測点を取得します。
3. **空間結合・集計**（`services/aggregator.py`）
   平面直角座標系（EPSG:6679）に変換し、各観測点を最寄りの道路区間に紐付け（50m 超は除外）。区間ごとに以下を算出します。
   - `wips`: 期間内の平均値
   - `road_surface` / `image_path`: グループ内の最後の観測
   - `last_updated`: 最新の観測時刻

   データのない区間も「データなし」として出力に含めます。
4. **表示**（`static/js/`）
   区間ごとに色分けして描画します。時間スライダーの絞り込みはサーバー通信なしで、クライアント側で `last_updated` を使って行います。

### 表示の凡例

| モード | 区分 | 色 |
|---|---|---|
| WIPS | 8.0 以上: 良好 | 青 |
| WIPS | 7.5 超 〜 8.0 未満: 注意 | 橙 |
| WIPS | 7.5 以下: 危険 | 赤 |
| 路面状態 | dry（乾燥） / wet（湿潤） / semi-wet（半湿潤） / fresh（新雪・積雪） / slush（シャーベット） / ice（凍結） | 緑 / 青 / シアン / 水色 / 茶 / 紫 |
| 共通 | データなし | 灰色の細線 |

---

## ディレクトリ構成

```
.
├── app.py                 # Flask アプリ本体（画面・API）
├── config.py              # パス・対象道路種別・既定の時間幅
├── generate_cache.py      # 直近24hキャッシュ生成（cron から実行）
├── requirements.txt
├── geojson.tar.xz         # 道路データ（N13）の圧縮ファイル → 展開して geojson/ に
├── services/
│   ├── road_loader.py     # 道路 GeoJSON の読み込み・種別フィルタ・路線名整形
│   ├── db_connector.py    # SQLite から観測データ取得
│   └── aggregator.py      # 最寄り道路への空間結合・区間集計
├── templates/
│   └── index.html         # 画面テンプレート
├── static/
│   ├── css/style.css
│   ├── js/
│   │   ├── state.js              # 共通状態（AppState）
│   │   ├── app_main.js           # 地図初期化・データ取得・詳細表示・自動更新
│   │   ├── styles_and_filter.js  # 色分け・凡例・フィルタ
│   │   ├── slider.js             # 時間スライダー
│   │   ├── history_modal.js      # 過去データ検索モーダル
│   │   └── connector_line.js     # 選択区間→パネルの矢印線
│   └── images/            # 路面画像（※リポジトリ外。シンボリックリンクで配置）
└── docs/
    └── issues_report.md   # 課題点レポート
```

Git 管理外（`.gitignore`）: `database.db`, `geojson/`, `output_24h.json`, `*.log`, `venv/`, `.archive/` など。

---

## セットアップ

### 前提

- Python 3.12（動作確認環境）
- SQLite データベース（`pointed_road_data` テーブル）
- 路面画像ディレクトリ

### 手順

```bash
# 1. データベースへのリンクを張る（ファイル名は database.db）
ln -s /path/to/本番DB.db database.db

# 2. 路面画像へのリンクを張る（パスは旧インターフェースを参照）
ln -s /path/to/images static/images

# 3. 道路データ（GeoJSON）を展開 → ./geojson/ が作成される
tar xvJf geojson.tar.xz

# 4. 仮想環境の作成とライブラリのインストール
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

# 5. 初回キャッシュの生成（output_24h.json が作られる）
venv/bin/python generate_cache.py

# 6. 起動
venv/bin/python app.py
```

起動時に道路データの読み込みで数秒かかります（「ロード完了。」と表示されれば準備完了）。

### アクセス URL

アプリは URL プレフィックス `/WinterRoad-Overview-LineStyle` を前提に動作します（`app.py` の `PrefixMiddleware`）。

- **Apache 経由（本番）**: `http(s)://<サーバー>/WinterRoad-Overview-LineStyle/`
- **直接アクセス**: `http://127.0.0.1:5100/`
  ※ HTML 内の CSS/JS のパスにもプレフィックスが付くため、直接アクセスでは静的ファイルが 404 になり表示が崩れます。ローカル確認時は Apache 経由にするか、`app.py` の `prefix` を一時的に空文字にしてください。

### 路面画像のパス規則

画像は `static/images/` 以下に次の構成で置かれている前提です（`static/js/app_main.js`）。

```
static/images/_indicated_bus_<バス記号>/<YYMMDD>/<image_path>
例) image_path = image_200126_054812_1_bus_A.jpg
    → static/images/_indicated_bus_A/200126/image_200126_054812_1_bus_A.jpg
```

---

## 定期実行（cron）

直近24時間キャッシュを 5 分ごとに更新します。`crontab -e` で以下を追加してください（`<アプリのルートパス>` は実際のパスに置き換え）。

```cron
*/5 * * * * cd <アプリのルートパス> && venv/bin/python ./generate_cache.py >> cron.log 2>&1
```

`generate_cache.py` は一時ファイルに書き出してから置き換えるため、読み込み中のファイル破損は起きません。

---

## Apache の設定

リバースプロキシで公開します。サーバーの VirtualHost 設定ファイルに以下を追記します（`mod_proxy`, `mod_proxy_http` が必要）。

```apache
<Location /WinterRoad-Overview-LineStyle>
    Require method GET

    ProxyPreserveHost On
    ProxyPass http://127.0.0.1:5100/
    ProxyPassReverse http://127.0.0.1:5100/
</Location>
```

```bash
sudo apache2ctl configtest      # 構文テスト
sudo systemctl restart apache2  # 再起動
```

---

## 設定

| 項目 | 設定場所 | 既定値 | 内容 |
|---|---|---|---|
| `GEOJSON_DIR` | 環境変数 / `config.py` | `./geojson` | 道路 GeoJSON のディレクトリ |
| `DB_PATH` | 環境変数 / `config.py` | `./database.db` | SQLite DB のパス |
| `TARGET_ROAD_TYPES` | `config.py` | `{'1', '2', '4'}` | 表示対象の道路種別（`N13_003` の値） |
| `DEFAULT_TIME_HOURS` | `config.py` | `24` | キャッシュの対象時間幅 |
| ポート | `app.py` | `5100` | Flask の待受ポート |
| URL プレフィックス | `app.py` | `/WinterRoad-Overview-LineStyle` | Apache の公開パスと合わせる |
| 紐付け距離 | `services/aggregator.py` | `50` m | これより遠い観測点は除外 |
| WIPS 閾値 | `static/js/styles_and_filter.js` | `7.5` / `8.0` | 危険 / 注意 の境界 |

---

## API

| メソッド | パス | パラメータ | 内容 |
|---|---|---|---|
| GET | `/api/roads/recent` | なし | `output_24h.json`（直近24h集計）を返す。未生成時は空の FeatureCollection |
| GET | `/api/roads/search` | `start_time`, `end_time`（`YYYY-MM-DD HH:MM:SS`） | 指定期間を DB から検索・集計して返す |

レスポンスは GeoJSON FeatureCollection です。各区間の `properties` には N13 の属性に加え、`display_route_name`, `wips`, `road_surface`, `last_updated`, `image_path` が入ります（データなしの区間は `null`）。

---

## データベース

主に使用するテーブル:

```sql
CREATE TABLE pointed_road_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude FLOAT,
    longitude FLOAT,
    get_at DATETIME,       -- 観測時刻 'YYYY-MM-DD HH:MM:SS'
    WIPS REAL,
    image_path TEXT,       -- 例: image_200126_054812_1_bus_A.jpg
    road_surface TEXT,     -- dry / wet / semi-wet / fresh / slush / ice
    mesh_1km_id INTEGER,
    mesh_10km_id INTEGER
);
```

`mesh_1km` / `mesh_10km` テーブルも存在しますが、現在のアプリでは使用していません。

---

## メモ

### `.tar.xz` について

`.tar.gz` の進化版。圧縮効率が非常に良いが、時間がかかる。
（参考: [圧縮解凍チートシート](https://qiita.com/wnoguchi/items/cb0fa7c11b119e96f1e5)）

```bash
tar cvJf hogehoge.tar.xz hogehoge/   # 圧縮
tar xvJf hogehoge.tar.xz             # 解凍
```
