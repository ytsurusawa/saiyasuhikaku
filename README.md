# 最安比較（saiyasuhikaku）

Amazon・楽天市場・Yahoo!ショッピング・価格.com など**日本でよく使う通販サイトを一括比較**し、
**送料込み・ポイント還元込みの「実質価格」**で「結局どこで買うのが一番お得か」を示します。

表示価格が最安でも、送料やポイント還元を入れると順位が逆転することは珍しくありません。
このツールはその逆転を明示します。

```
$ python -m saiyasu "Anker Prime Charger 65W" --spu 5 --lyp --gonotsuku --prime

 順位 │  プラットフォーム  │ 商品価格 │ 送料  │ 手数料 │ ポイント │ 実質価格 │ 1位との差
──────┼────────────────────┼──────────┼───────┼────────┼──────────┼──────────┼───────────
 ★1  │ ヨドバシ.com       │ 47,600円 │  無料 │      - │ -4,760円 │ 42,840円 │        —
  2   │ Qoo10              │ 47,890円 │  無料 │      - │        - │ 43,101円 │    +261円
  3   │ ビックカメラ.com   │ 47,940円 │  無料 │      - │ -4,794円 │ 43,146円 │    +306円
  4   │ 楽天市場           │ 49,560円 │  無料 │      - │ -3,617円 │ 45,943円 │  +3,103円
  5   │ 価格.com           │ 45,420円 │ 800円 │      - │        - │ 46,220円 │  +3,380円
  6   │ Amazon.co.jp       │ 46,810円 │  無料 │      - │   -468円 │ 46,342円 │  +3,502円
  7   │ Yahoo!ショッピング │ 50,240円 │  無料 │      - │ -3,666円 │ 46,574円 │  +3,734円
  8   │ au PAY マーケット  │ 50,270円 │  無料 │      - │ -2,764円 │ 47,506円 │  +4,666円

◎ 結論: 最もお得なのは【ヨドバシ.com】の実質 42,840円(支払 47,600円 − ポイント 4,760円相当)です。
　　　　2位のQoo10より 261円お得。※表示価格だけなら価格.comが最安ですが、送料とポイントを
　　　　入れると順位が逆転します。
```

> 上の数値はAPIキー未設定時のサンプルデータによる実行例です。

## 実質価格の計算

```
支払総額 = 商品価格 + 送料 + 手数料 − クーポン
実質価格 = 支払総額 − 獲得ポイントの円換算価値
```

考慮している要素：

- **送料** … 送料込み／一律／「◯◯円以上で無料」の条件判定、沖縄・離島の追加送料
- **ポイント還元** … 基本ポイント、ショップ独自ポイント、楽天SPU、買い回り（上限 +9%）、
  LYPプレミアム、5のつく日、PayPayステップ、Amazonカードなど
- **ポイントの価値** … 期間限定ポイントは使い道が限られるため、既定では 1pt = 0.9円 として評価
  （通常ポイントは 1pt = 1円。どちらも設定で変更可）
- **獲得上限** … キャンペーンポイントの上限（cap）
- **クーポン** … 即時値引き。ポイントは値引き後の金額を基準に計算
- **中古** … メルカリなどの中古出品は既定で除外（オプトインで比較に含められる）

## 対応プラットフォーム

| プラットフォーム | データ取得方法 | 必要な設定 |
| --- | --- | --- |
| Amazon.co.jp | Product Advertising API v5（SigV4署名を内製） | `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY` / `AMAZON_PARTNER_TAG` |
| 楽天市場 | 楽天ウェブサービス 商品検索API | `RAKUTEN_APP_ID`（任意で `RAKUTEN_AFFILIATE_ID`） |
| Yahoo!ショッピング | 商品検索API v3 | `YAHOO_APP_ID` |
| 価格.com | 手動入力 / CSV・JSON取り込み | `data/manual_offers.json` |
| ヨドバシ.com | 同上 | 同上 |
| ビックカメラ.com | 同上 | 同上 |
| au PAY マーケット | 同上 | 同上 |
| Qoo10 | 同上 | 同上 |
| メルカリ | 同上 | 同上 |

> 価格.com・ヨドバシ・ビックカメラ・au PAY マーケット・Qoo10・メルカリには、誰でも使える公開の
> 商品検索APIがありません。これらは手動入力（または自前の取得処理）のデータを読み込んで比較に混ぜます。
> **APIキーを設定していないプラットフォームは、動作確認用のサンプル（デモ）データで表示され、
> 画面・CLIの両方に「サンプル」と明示されます。**

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env      # 取得したAPIキーを記入（任意）
```

APIキーは環境変数で渡します。未設定でもサンプルデータで一通り動作します。

## 使い方

### CLI

```bash
python -m saiyasu "Anker 充電器 65W"

# ポイント条件を指定（楽天SPU +5%、LYPプレミアム、5のつく日、プライム会員）
python -m saiyasu "Anker 充電器 65W" --spu 5 --lyp --gonotsuku --prime

# 楽天の買い回り10店舗、沖縄・離島、中古も含める
python -m saiyasu "ゲーム機" --kaimawari 10 --remote --used

# 比較対象を絞る／JSONで出力
python -m saiyasu "炊飯器" --platforms amazon,rakuten,yahoo --json
```

主なオプションは `python -m saiyasu --help` で確認できます。

### Web画面

```bash
uvicorn saiyasu.api:app --reload
# http://127.0.0.1:8000/
```

商品名を入れて「一括比較」を押すと、実質価格の安い順に並びます。
バーの長さが支払総額、斜線部分がポイントで戻る分、太字が実質価格です。
ダークモード・スマートフォン表示に対応しています。

### Web API

```bash
curl -X POST http://127.0.0.1:8000/api/compare \
  -H 'Content-Type: application/json' \
  -d '{"query":"Anker 充電器 65W","profile":{"rakuten_spu_rate":0.05,"lyp_premium":true}}'
```

| エンドポイント | 説明 |
| --- | --- |
| `POST /api/compare` | 一括比較。実質価格の安い順に結果と内訳を返す |
| `GET /api/platforms` | 比較対象と、各プラットフォームの取得可否・必要な環境変数 |
| `GET /healthz` | ヘルスチェック |

### Pythonから使う

```python
from saiyasu import Comparator, PointProfile

result = Comparator().compare(
    "Anker 充電器 65W",
    profile=PointProfile(rakuten_spu_rate=0.05, lyp_premium=True, yahoo_day_campaign=True),
)
print(result.verdict())
for row in result.ranked:
    print(row.rank, row.offer.platform_label, row.breakdown.effective_price)
```

## 公開APIが無いサイトの価格を入れる

`data/manual_offers.example.json` を `data/manual_offers.json` にコピーして編集します。
検索語は商品名・ショップ名への部分一致で絞り込まれます。

```json
{
  "kakaku": [
    {
      "title": "Anker Prime Charger 65W",
      "price": 8480,
      "shop": "最安ショップA",
      "shipping": { "kind": "flat", "fee": 800 },
      "points": []
    }
  ],
  "yodobashi": [
    {
      "title": "Anker Prime Charger 65W",
      "price": 8980,
      "shipping": { "kind": "free" },
      "points": [{ "label": "ゴールドポイント10%", "rate": 0.1 }]
    }
  ]
}
```

`shipping.kind` は `free` / `flat` / `conditional_free` / `unknown`、
`points[].rate` は小数（`0.1` = 10%）で指定します。
`limited: true` を付けると期間限定ポイントとして割り引いて評価されます。

## 新しいプラットフォームを足す

`saiyasu/platforms/base.py` の `PlatformAdapter` を実装し、`registry.py` の `ADAPTERS` に追加します。

```python
class MyShopAdapter(PlatformAdapter):
    key = "myshop"
    label = "マイショップ"
    required_env = ("MYSHOP_API_KEY",)

    def search(self, ctx: SearchContext) -> list[Offer]:
        ...  # Offer のリストを返す
```

送料・ポイントの表現は `ShippingPolicy` と `PointReward` に寄せてあるため、
計算・ランキング・表示側の変更は不要です。

## テスト

```bash
python -m pytest -q
```

## 注意事項

- サンプル（デモ）データは動作確認用の**架空の価格**です。実際の購入判断には使えません。
  実データで比較するには各プラットフォームのAPIキーを設定してください。
- 送料は「3,980円以上で無料」などショップごとの条件に依存します。APIから確定値が取れない場合は
  推定値を使い、画面・CLIで「要確認」と表示します。最終的な金額は購入前に各サイトでご確認ください。
- ポイント還元率はキャンペーンや会員ランクで変動します。設定値はご自身の条件に合わせてください。
- 各サイトのAPI利用規約・レート制限を守ってご利用ください。スクレイピングは行いません。
