# 冬季道路情報提供インターフェース（線的表示）
### 起動方法
データベースのリンクを張る(database.dbとする)

画像へのリンクを張る(パスは旧インターフェース参照)
```
tar xvJf geojson.tar.xz #地理空間情報の解凍
python3 -m venv .venv #仮想環境作成
. .venv/bin/activate #仮想環境起動
pip install -r requirements.txt #ライブラリインストール
.venv/bin/python app.py
```
現在はhttp://127.0.0.1:5100/　で開く

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

### アパッチの設定
stakahashi*****netの設定ファイルを開いて下を追記
```
    <Location /WinterRoad-Overview-LineStyle>
	Require method GET

	ProxyPreserveHost On
	ProxyPass http://127.0.0.1:5100/
	ProxyPassReverse http://127.0.0.1:5100/
    </Location>

```
```
sudo apache2ctl configtest #構文テスト
sudo systemctl restart apache2　#再起動
```