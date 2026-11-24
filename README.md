# 冬季道路情報提供インターフェース（線的表示）

車両（路線バス等）に搭載したカメラの画像から推定した **視界（WIPS）** と **路面状態** を、北海道の主要道路網に紐付けて、**道路区間ごとに色分け表示** する Web アプリケーションです（プロトタイプ）。

- 直近24時間の状況を表示し、5分ごとに自動更新
- 時間スライダー・プリセットで表示範囲を指定（範囲内の観測で代表点を選び直す）
- 過去の任意の期間（最大7日）を検索
- 区間をクリックすると、WIPS・路面状態・観測時刻・路面画像・推移グラフを表示
- 注意が必要な区間の一覧、地名検索・現在地、表示状態の URL 共有、スマートフォン対応

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
              GET /healthz                   キャッシュの鮮度（監視用）
                   ▲
                   │ リバースプロキシ (/WinterRoad-Overview-LineStyle)
                Apache
                   ▲
                ブラウザ（Leaflet + 国土地理院 淡色地図 + noUiSlider）
```

### 処理の流れ

1. **道路データ**（`services/road_loader.py`）
   `geojson/` の国土数値情報 道路（N13）から、`N13_003`（道路分類）が対象（既定: 国道・都道府県道・高速自動車国道等）の区間を抽出します。抽出結果は `cache/roads_<署名>.pkl` に保存し、元ファイルが変わるまで再利用します。抽出順の番号が **区間ID（seg_id）** です。
2. **観測データ**（`services/db_connector.py`）
   期間内の観測を時刻順に取得し、クレンジングします（時刻・位置の不正な行を除外、WIPS の ±Inf などを欠損扱い、画像名から車両記号を抽出）。
3. **紐付け**（`services/matcher.py`）
   平面直角座標系（EPSG:6679）で、各観測を最寄りの区間に紐付けます。50m より遠い観測は除外します。
4. **代表点の選出**（`services/representative.py`）
   区間ごとに **「最新通過内の最小WIPS観測」** を代表点とします。同じ車両の連続した観測（間隔10分以内）を1回の「通過」とみなし、最も新しい通過の中で WIPS が最も低い（視界が悪い）観測を選びます。WIPS・路面状態・時刻・画像はすべてこの1観測のものです。詳しくは[提案書](docs/representative_point_algorithms.md)を参照してください。
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
│   └── status_service.py   # API 用の組み立て、キャッシュ、過去検索の制御
├── templates/index.html
├── static/
│   ├── css/style.css
│   ├── js/                 # ES Modules
│   │   ├── main.js         # 起動・更新フロー
│   │   ├── roadmap.js      # 地図・道路レイヤー・選択の強調
│   │   ├── timebar.js      # 時間スライダー
│   │   ├── panel.js        # 凡例/フィルタ・注意区間一覧・詳細・推移グラフ
│   │   ├── dialogs.js      # 過去検索・画像拡大・ヘルプ・地名検索
│   │   ├── categories.js   # 区分と配色
│   │   ├── state.js        # 状態・URL・設定の保存
│   │   ├── connector.js    # 選択区間→詳細パネルの引き出し線
│   │   ├── api.js / time.js
│   ├── vendor/             # Leaflet 1.9.4, noUiSlider 15.7.1（同梱）
│   └── images/             # 路面画像（※リポジトリ外。シンボリックリンクで配置）
├── scripts/create_indexes.sql  # DB インデックス（DB 管理者と調整のうえ適用）
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
| `WIPS_VALID_MIN` / `WIPS_VALID_MAX` | なし | 範囲外の WIPS を欠損扱いにする |
| `WIPS_EXCLUDED_BUSES` | なし | WIPS を欠損扱いにする車両（例: `J,K`）。路面状態は残す |

`config.py` で変更する値:

| 名前 | 既定値 | 内容 |
|---|---|---|
| `TARGET_ROAD_TYPES` | `{'1','2','4'}` | 対象の道路分類（N13_003: 1=国道, 2=都道府県道, 4=高速自動車国道等） |
| `LIVE_WINDOW_HOURS` | 24 | 現在モードの時間幅 |
| `MAX_SEARCH_DAYS` | 7 | 過去検索の最大日数 |
| `MATCH_DISTANCE_M` | 50 | 紐付けの最大距離 [m] |
| `PASS_GAP_MINUTES` | 10 | 同一車両の観測をこの間隔で「別の通過」とみなす [分] |
| `WIPS_DANGER_MAX` / `WIPS_WARN_MAX` | 7.5 / 8.0 | 視程不良 / 注意 の閾値 |
| `CACHE_STALE_MINUTES` | 15 | キャッシュが古いと判定する時間 [分] |
| `MAX_CONCURRENT_SEARCHES` | 2 | 過去検索の同時実行数の上限（超えると 503） |

---

## API

時刻はすべて `YYYY-MM-DD HH:MM:SS`（日本時間）。

| パス | パラメータ | 内容 |
|---|---|---|
| `GET /api/roads/geometry` | — | 全区間の形状（GeoJSON）。`properties.id` が区間ID |
| `GET /api/roads/status` | `base_start`, `base_end`（過去検索の期間。省略時は直近24h）<br>`start`, `end`（その中で代表点を選ぶ範囲。省略時は全体） | 区間ID → 代表点（`wips`, `road_surface`, `observed_at`, `age_minutes`, `image_url`, `bus`, `pass`, `stats`）と、期間・鮮度などのメタ情報 |
| `GET /api/roads/<id>/timeline` | `status` と同じ | 区間の観測一覧（時刻・WIPS・路面・車両・通過番号） |
| `GET /healthz` | — | `ok`（200）/ `stale`・`no_cache`（503） |

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
- 期間検索の高速化には `get_at` のインデックスが有効です（`scripts/create_indexes.sql`）。DB は共有のため、適用は DB 管理者と調整してください。

---

## テスト

```bash
pip install -r requirements-dev.txt
python -m pytest tests              # 単体・API・E2E（約15秒）
python -m pytest tests --ignore=tests/e2e   # ブラウザなしの場合
```

- テストは一時ディレクトリに作る小さな固定データ（道路4本・観測13件）で実行するため、`database.db` には触れません。
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
