# 冬季道路情報提供インターフェース（線的表示）
### 起動方法
データベースのリンクを張る(database.dbとする)

画像へのリンクを張る(パスは旧インターフェース参照)
```
tar xvzf geojson.tar.gz #地理空間情報の解凍
python3 -m venv .venv #仮想環境作成
. .venv/bin/activate #仮想環境起動
pip install -r requirements.txt #ライブラリインストール
.venv/bin/python app.py
```
現在はhttp://127.0.0.1:5000/　で開く

cronに以下を追加
`*/5 * * * * cd ＃インターフェースのアプリルートパス; venv/bin/python ./generate_cache.py >> cron.log 2>&1`

#### memo
##### `.tar.xz`
`.tar.gz`の進化版　圧縮効率が超いいが時間かかる

[圧縮解凍チートシート](!https://qiita.com/wnoguchi/items/cb0fa7c11b119e96f1e5)

圧縮
`tar cvJf hogehoge.tar.xz hogehoge/`

解凍
`tar xvJf hogehoge.tar.xz`