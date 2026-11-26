# 冬季道路情報提供インターフェース（線的表示）

車両（路線バス等）に搭載したカメラの画像から推定した **視界（WIPS）** と **路面状態** を、北海道の主要道路網に紐付けて、**道路区間ごとに色分け表示** する Web アプリケーションです（プロトタイプ）。

- 直近24時間の状況を表示し、5分ごとに自動更新
- 時間スライダー・プリセットで表示範囲を指定（範囲内の観測で代表点を選び直す）
- 過去の任意の期間（最大7日）を検索
- 区間をクリックすると、WIPS・路面状態・観測時刻・路面画像を表示
- バスの現在位置（観測時刻が5分以内の最新観測）をアイコンで表示
- 注意が必要な区間の一覧（路線 × 市町村ごとにまとめて表示）、地名検索・現在地、表示状態の URL 共有、スマートフォン対応

> 本リポジトリの `database.db` はテストデータです。本番環境では観測データがリアルタイムに送信され、DB に随時登録されます。

関連ドキュメント:
- [`docs/issues_report.md`](docs/issues_report.md) … 課題点レポートと対応状況
- [`docs/representative_point_algorithms.md`](docs/representative_point_algorithms.md) … 区間代表点の選出アルゴリズム（提案と採用方式）

---

## システム構成

```
観測データ（車載カメラ）
        │  リアルタイム登録
        ▼
SQLite: database.db (pointed_road_data) ※他システムと共有。アプリは読み取り専用で開く
        │
        ├─ cron (5分毎): generate_cache.py
        │     直近24hを抽出 → クレンジング → 最寄り道路へ紐付け(50m以内)
        │     → cache/recent_matched.pkl（アトミックに置換）
        │
        └─ Flask: app.py (:5100)
              GET /                          画面
              GET /api/roads/geometry        道路形状（gzip・ETag でブラウザにキャッシュ）
              GET /api/roads/status          区間ごとの代表点（現在/過去、表示範囲指定）
              GET /api/roads/<id>/timeline   区間の観測の推移
              GET /api/roads/recent, /search 旧API（互換のため残している）
              GET /api/buses                 バスの現在位置（5分以内の最新観測）
              GET /healthz                   キャッシュの鮮度（監視用）
                   ▲
                   │ リバースプロキシ (/WinterRoad-Overview-LineStyle)
                Apache
                   ▲
                ブラウザ（Leaflet + 国土地理院 淡色地図 + noUiSlider）
```

### 処理の流れ

1. **道路データ**（`services/road_loader.py`）
   `geojson/` の国土数値情報 道路（N13）から、`N13_003`（道路分類）が対象（既定: 国道・都道府県道・高速自動車国道等）の区間を抽出します。`data/road_attributes.csv` があれば路線名・市町村を付けます（[後述](#路線名市町村データ)）。抽出結果は `cache/roads_<署名>.pkl` に保存し、元ファイルが変わるまで再利用します。抽出順の番号が **区間ID（seg_id）** です。
2. **観測データ**（`services/db_connector.py`）
   期間内の観測を時刻順に取得し、クレンジングします（時刻・位置の不正な行を除外、WIPS の ±Inf などを欠損扱い、画像名から車両記号を抽出）。
3. **紐付け**（`services/matcher.py`）
   平面直角座標系（EPSG:6679）で、各観測を最寄りの区間に紐付けます。50m より遠い観測は除外します。
4. **代表点の選出**（`services/representative.py`）
   区間ごとに **「最新通過の中央値」（提案書の方式 H）** で代表点を選びます。同じ車両の連続した観測（間隔10分以内）を1回の「通過」とみなし、最も新しい通過の WIPS 中央値に最も近い観測を選びます（等距離なら WIPS の低い方）。WIPS・路面状態・時刻・画像はすべてこの1観測のものです。詳しくは[提案書](docs/representative_point_algorithms.md)を参照してください。
5. **表示**（`static/js/`）
   道路形状は初回に1回だけ取得し、状態値（区間ID→代表点）だけを更新・再描画します。

### 表示の凡例

| 指標 | 区分（危険度の低い順） | 色 |
|---|---|---|
| 視界（WIPS） | 8.0 以上: 良好 / 7.5 超〜8.0 未満: 注意 / 7.5 以下: 視程不良 | 青 / 黄 / 赤 |
| 路面状態 | 乾燥 / 半湿潤 / 湿潤 / シャーベット / 積雪（新雪）/ 凍結 | 青 / 青緑 / 緑 / 黄 / 橙 / 赤 |
| 共通 | 期間内に観測なし | 灰色の細線 |

線が薄いほど観測からの経過時間が長いことを表します（1時間以内・3時間以内・6時間以内・それ以上の4段階）。

**WIPS**（Weighted Intensity of Power Spectra）は、画像の空間周波数成分の強さから視程を評価する指標です（Hagiwara et al., 2006）。視程が悪いほど画像の細部が失われ、値が小さくなります。本システムでは、画像中央 256×256 画素の2次元 FFT のうち直流付近を除いた周波数帯のパワーを合計し、その対数をとった値を用いています。

> Hagiwara, T., Ota, Y., Kaneda, Y., Nagata, Y., & Araki, K. (2006). Method of Processing Closed-Circuit Television Digital Images for Poor Visibility Identification. *Transportation Research Record*, 1973(1), 95–104. https://doi.org/10.1177/0361198106197300112

---

## ディレクトリ構成

```
.
├── app.py                  # Flask アプリ（画面・API）
├── config.py               # 設定（環境変数で上書き可）
├── generate_cache.py       # 直近24hキャッシュ生成（cron から実行）
├── requirements.txt        # 本番用ライブラリ
├── requirements-dev.txt    # テスト用（pytest, playwright）
├── geojson.tar.xz          # 道路データ（N13）→ 展開して geojson/ に
├── services/
│   ├── road_loader.py      # 道路データの読み込み・抽出・キャッシュ
│   ├── db_connector.py     # 観測データの取得・クレンジング（読み取り専用）
│   ├── matcher.py          # 観測→道路区間の紐付け
│   ├── representative.py   # 代表点の選出アルゴリズム
│   ├── status_service.py   # API 用の組み立て、キャッシュ、過去検索の制御
│   ├── bus_service.py      # バスの現在位置
│   └── legacy_api.py       # 旧API（/recent, /search）の互換出力
├── data/
│   ├── road_attributes.csv       # 区間ごとの路線名・市町村（下記スクリプトで生成）
│   └── road_attributes.meta.json # 生成日時・出典・付与率
├── templates/index.html
├── static/
│   ├── css/style.css
│   ├── js/                 # ES Modules
│   │   ├── main.js         # 起動・更新フロー
│   │   ├── roadmap.js      # 地図・道路レイヤー・選択の強調
│   │   ├── buses.js        # バスの現在位置
│   │   ├── timebar.js      # 時間スライダー
│   │   ├── panel.js        # 凡例/フィルタ・注意区間一覧・詳細
│   │   ├── alerts.js       # 注意区間を路線 × 市町村ごとにまとめる
│   │   ├── dialogs.js      # 過去検索・画像拡大・ヘルプ・地名検索
│   │   ├── categories.js   # 区分と配色
│   │   ├── state.js        # 状態・URL・設定の保存
│   │   ├── connector.js    # 選択区間→詳細パネルの引き出し線
│   │   ├── api.js / time.js
│   ├── vendor/             # Leaflet 1.9.4, noUiSlider 15.7.1（同梱）
│   └── images/             # 路面画像（※リポジトリ外。シンボリックリンクで配置）
├── scripts/
│   ├── build_road_attributes.py  # 路線名・市町村の付与（OSM・行政区域と突合。オフライン）
│   └── create_indexes.sql        # DB インデックス（DB 管理者と調整のうえ適用）
├── tests/                  # 単体・API・E2E テスト
└── docs/
```

Git 管理外（`.gitignore`）: `database.db`, `geojson/`, `cache/`, `*.log`, `venv/`, `.archive/` など。

---

## セットアップ

### 前提

- Python 3.12（動作確認環境）
- SQLite データベース（`pointed_road_data` テーブル）
- 路面画像ディレクトリ

### 手順

```bash
# 1. データベースへのリンク（ファイル名は database.db）
ln -s /path/to/本番DB.db database.db

# 2. 路面画像へのリンク（パスは旧インターフェースを参照）
ln -s /path/to/images static/images

# 3. 道路データ（GeoJSON）を展開 → ./geojson/
tar xvJf geojson.tar.xz

# 4. 仮想環境とライブラリ
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

# 5. 初回キャッシュの生成（初回のみ GeoJSON の解析に数秒かかる）
venv/bin/python generate_cache.py

# 6. 起動
venv/bin/python app.py
```

### アクセス URL

- Apache 経由（本番）: `http(s)://<サーバー>/WinterRoad-Overview-LineStyle/`
- 直接: `http://127.0.0.1:5100/`（プレフィックス付きの `http://127.0.0.1:5100/WinterRoad-Overview-LineStyle/` でも可）

### テストデータで動かす場合

テストDB の最新データは 2026-11-05 のため、そのままでは「直近24時間」にデータがありません。基準時刻を固定して動かせます（**本番では設定しないこと**）。

```bash
export APP_FIXED_NOW="2026-11-05 12:30:00"
venv/bin/python generate_cache.py
venv/bin/python app.py
```

### 路面画像のパス規則

```
static/images/_indicated_bus_<車両記号>/<DDMMYY>/<image_path>
例) image_path = image_051126_121550_1_bus_J.jpg
    → static/images/_indicated_bus_J/051126/image_051126_121550_1_bus_J.jpg
```

画像名が `image_<DDMMYY>_<HHMMSS>_<番号>_bus_<車両記号>.jpg` の形式でない場合、画像は表示されません。

---

## 定期実行（cron）

直近24時間キャッシュを5分ごとに更新します（`<アプリのルートパス>` は実際のパスに置き換え）。

```cron
*/5 * * * * cd <アプリのルートパス> && venv/bin/python ./generate_cache.py >> cron.log 2>&1
```

- 書き込みは一時ファイル経由のアトミック置換なので、読み込み中のファイルは壊れません。
- 失敗すると終了コード 1 を返し、`cron.log` にスタックトレースを出力します。
- キャッシュが15分以上更新されないと、画面に警告が表示され、`/healthz` が `503 {"status": "stale"}` を返します。

`cron.log` のローテーション例（`/etc/logrotate.d/winterroad-linestyle`）:

```
<アプリのルートパス>/cron.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

---

## Apache の設定

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

アプリ側で JSON を gzip 圧縮して返すため、Apache 側の圧縮設定は不要です（`mod_deflate` が有効でも二重圧縮はされません）。

---

## 設定

環境変数で上書きできます（`config.py`）。

| 環境変数 | 既定値 | 内容 |
|---|---|---|
| `DB_PATH` | `./database.db` | SQLite DB のパス |
| `GEOJSON_DIR` | `./geojson` | 道路 GeoJSON のディレクトリ |
| `CACHE_DIR` | `./cache` | キャッシュの出力先 |
| `APP_PREFIX` | `/WinterRoad-Overview-LineStyle` | Apache の公開パス |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `5100` | 待受アドレス・ポート |
| `APP_TIMEZONE` | `Asia/Tokyo` | DB の時刻（`get_at`）のタイムゾーン |
| `APP_FIXED_NOW` | なし | テスト用に基準時刻を固定（本番では設定しない） |
| `ROAD_ATTRIBUTES_PATH` | `./data/road_attributes.csv` | 路線名・市町村データ。なければ道路分類で表示 |
| `WIPS_VALID_MIN` / `WIPS_VALID_MAX` | なし | 範囲外の WIPS を欠損扱いにする |

`config.py` で変更する値:

| 名前 | 既定値 | 内容 |
|---|---|---|
| `TARGET_ROAD_TYPES` | `{'1','2','4'}` | 対象の道路分類（N13_003: 1=国道, 2=都道府県道, 4=高速自動車国道等） |
| `LIVE_WINDOW_HOURS` | 24 | 現在モードの時間幅 |
| `MAX_SEARCH_DAYS` | 7 | 過去検索の最大日数 |
| `MATCH_DISTANCE_M` | 50 | 紐付けの最大距離 [m] |
| `REPRESENTATIVE_METHOD` | `latest_pass_median` | 代表点の方式（H: `latest_pass_median` 採用 / B: `latest_pass_min_wips` 比較用）。環境変数でも指定可 |
| `PASS_GAP_MINUTES` | 10 | 同一車両の観測をこの間隔で「別の通過」とみなす [分] |
| `WIPS_DANGER_MAX` / `WIPS_WARN_MAX` | 7.5 / 8.0 | 視程不良 / 注意 の閾値 |
| `CACHE_STALE_MINUTES` | 15 | キャッシュが古いと判定する時間 [分] |
| `BUS_RECENT_MINUTES` / `BUS_MERGE_DISTANCE_M` | 5 / 100 | バスの現在位置: 対象とする観測の新しさ [分] / 1つにまとめる距離 [m] |
| `MAX_CONCURRENT_SEARCHES` | 2 | 過去検索の同時実行数の上限（超えると 503） |

---

## API

時刻はすべて `YYYY-MM-DD HH:MM:SS`（日本時間）。

| パス | パラメータ | 内容 |
|---|---|---|
| `GET /api/roads/geometry` | — | 全区間の形状（GeoJSON）。`properties.id` が区間ID |
| `GET /api/roads/status` | `base_start`, `base_end`（過去検索の期間。省略時は直近24h）<br>`start`, `end`（その中で代表点を選ぶ範囲。省略時は全体） | 区間ID → 代表点（`wips`, `road_surface`, `observed_at`, `age_minutes`, `image_url`, `bus`, `pass`, `stats`）と、期間・鮮度などのメタ情報 |
| `GET /api/roads/<id>/timeline` | `status` と同じ | 区間の観測一覧（時刻・WIPS・路面・車両・通過番号）。現在の画面では使っていない（調査用） |
| `GET /api/buses` | — | バスの現在位置。観測時刻が5分以内の観測から車両ごとに最新の1点を選び、100m 以内の点は最新の1点にまとめる。`bus`, `lat`, `lon`, `observed_at`, `age_seconds`, `heading`（進行方向、真北=0°）, `wips`, `road_surface`, `image_url`, `merged`（まとめられた車両）。車両記号は管理用のため画面には表示しない |
| `GET /healthz` | — | `ok`（200）/ `stale`・`no_cache`（503） |
| `GET /api/roads/recent` | — | **旧API**。直近24時間・全区間の GeoJSON。`properties` は N13 の元属性・`display_route_name`・`wips`（期間内平均）・`road_surface`・`last_updated`・`image_path` |
| `GET /api/roads/search` | `start_time`, `end_time` | **旧API**。指定期間（最大7日）で `/recent` と同じ形式 |

旧API は他システムでの利用を確認するまで残しています。旧実装からの変更点（不具合修正のみ）は [課題点レポート 8章](docs/issues_report.md#8-改修で新たに分かったこと変更点) を参照してください。

入力が不正な場合は `400 {"error": "理由"}`、過去検索が混雑している場合は `503` を返します。

---

## データベース

```sql
CREATE TABLE pointed_road_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude FLOAT,
    longitude FLOAT,
    get_at DATETIME,       -- 観測時刻 'YYYY-MM-DD HH:MM:SS'（日本時間）
    WIPS REAL,             -- 視界の指標（小さいほど視程不良）
    image_path TEXT,       -- 例: image_051126_121550_1_bus_J.jpg
    road_surface TEXT,     -- dry / semi-wet / wet / slush / fresh / ice
    mesh_1km_id INTEGER,
    mesh_10km_id INTEGER
);
```

- `mesh_1km` / `mesh_10km` テーブルは別システムで使用しています（本アプリでは未使用。削除しないこと）。
### インデックス（`scripts/create_indexes.sql`）— 導入決定（2026-11-25）

**何をするか**: `pointed_road_data` の `get_at`（観測時刻）列に索引（`idx_pointed_road_data_get_at`）を1つ追加します。テーブルのデータ・列は一切変更しません。`DROP INDEX` で元に戻せます。

**なぜ必要か**: このアプリは「ある期間の観測」を `WHERE get_at >= ? AND get_at <= ?` で取り出します（cron で5分ごとに直近24時間、過去検索で最大7日）。索引がないと SQLite は**毎回テーブル全行を読む**ため、DB が大きくなるほど遅くなります。本番は観測が増え続けるので、時間とともに cron・過去検索が遅くなっていきます。

**効果と影響**（テストDB 433MB・431万行のコピーで計測）:

| 項目 | 索引なし | 索引あり |
|---|---|---|
| 直近1時間の取得 | 446 ms | 1 ms |
| 直近24時間（cron と同じ） | 452 ms | 7 ms |
| 7日間 | 564 ms | 110 ms |
| 実行計画 | テーブル全件走査 | 索引で範囲検索 |
| DB ファイルサイズ | 433 MB | +121 MB |
| 観測の登録（INSERT 2000件） | 10.5 秒 | 10.8 秒（差は誤差程度） |

- 作成には約3秒かかり、その間は DB への書き込み（他システムの登録）が待たされます。登録の少ない時間帯に実行してください。
- 他システムの読み取り・書き込みの動作は変わりません（時刻で検索する処理があれば、それも速くなります）。

```bash
sqlite3 database.db < scripts/create_indexes.sql                              # 適用
sqlite3 database.db "DROP INDEX IF EXISTS idx_pointed_road_data_get_at;"      # 取り消し
```

アプリは起動時に索引の有無を確認し、なければログに警告を出します（`/healthz` の `db_time_index`）。

---

## 路線名・市町村データ

国土数値情報 道路（N13）には路線名の属性がないため、外部データと突合して `data/road_attributes.csv` を作っています。アプリはこの CSV だけを読むので、本番サーバーに外部データは不要です。

| 項目 | 出典 | 方法 |
|---|---|---|
| 路線名 | OpenStreetMap（[Geofabrik 北海道抽出](https://download.geofabrik.de/asia/japan/hokkaido.html)） | 区間に沿って約20mごとに標本点を取り、道路分類が対応する OSM の道（国道↔trunk、道道↔primary/secondary、高速↔motorway）のうち 20m 以内・向きの差 30° 以内で最も近いものを探す。標本点の 60% 以上が同じ路線なら採用 |
| 市町村・振興局 | [国土数値情報 行政区域（N03）](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2025.html) 北海道 | 区間の中点を含む行政区域 |

付与率（2025年1月版 N03、2026年11月の OSM）: 国道 98%・道道 95%・高速 74%（未付与の多くは IC ランプ）・市町村 100%。路線名が分からない区間は「国道（幅員5.5〜13m）」のように道路分類で表示します。

**道路データ（geojson）を差し替えたときは再生成してください**（区間の対応が取れない行は使われず、ログに警告が出ます）:

```bash
# 外部データを取得（作業用ディレクトリで）
curl -LO https://download.geofabrik.de/asia/japan/hokkaido-latest.osm.pbf
curl -LO https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2025/N03-20250101_01_GML.zip && unzip N03-20250101_01_GML.zip
# 生成（約1分）→ data/road_attributes.csv
venv/bin/python scripts/build_road_attributes.py --osm hokkaido-latest.osm.pbf --n03 N03-20250101_01.shp
# キャッシュを作り直してアプリを再起動
venv/bin/python generate_cache.py
```

**ライセンス**: 路線名は OpenStreetMap 由来のため、`road_attributes.csv` は [ODbL](https://opendatacommons.org/licenses/odbl/) の派生データベースにあたります。地図には「© OpenStreetMap contributors」を表示しています。CSV 自体を外部に公開・配布する場合は ODbL に従う必要があります。行政区域は国土数値情報（出典の記載が必要）です。

---

## テスト

```bash
pip install -r requirements-dev.txt
python -m pytest tests              # 単体・API・E2E（約15秒）
python -m pytest tests --ignore=tests/e2e   # ブラウザなしの場合
```

- テストは一時ディレクトリに作る小さな固定データ（道路4本・観測17件）で実行するため、`database.db` には触れません。
- E2E テストはシステムの Google Chrome を使います。ない場合は `playwright install chromium` を実行してください。

---

## メモ

### `.tar.xz` について

`.tar.gz` の進化版。圧縮効率が非常に良いが、時間がかかる。
（参考: [圧縮解凍チートシート](https://qiita.com/wnoguchi/items/cb0fa7c11b119e96f1e5)）

```bash
tar cvJf hogehoge.tar.xz hogehoge/   # 圧縮
tar xvJf hogehoge.tar.xz             # 解凍
```
