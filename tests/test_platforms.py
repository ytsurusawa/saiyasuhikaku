"""各プラットフォームアダプタのテスト(HTTPはモック)。"""

import json

import pytest

from saiyasu.platforms import SearchContext
from saiyasu.platforms.amazon import AmazonAdapter
from saiyasu.platforms.base import AdapterError
from saiyasu.platforms.demo import demo_offers
from saiyasu.platforms.manual import ManualAdapter
from saiyasu.platforms.rakuten import RakutenAdapter
from saiyasu.platforms.spec import offer_from_dict, shipping_from_dict
from saiyasu.platforms.yahoo import YahooAdapter

CTX = SearchContext(query="テスト商品", limit=3)


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def rakuten_env(monkeypatch):
    monkeypatch.setenv("RAKUTEN_APP_ID", "dummy")


@pytest.fixture
def yahoo_env(monkeypatch):
    monkeypatch.setenv("YAHOO_APP_ID", "dummy")


@pytest.fixture
def amazon_env(monkeypatch):
    monkeypatch.setenv("AMAZON_ACCESS_KEY", "AKIDEXAMPLE")
    monkeypatch.setenv("AMAZON_SECRET_KEY", "SECRET")
    monkeypatch.setenv("AMAZON_PARTNER_TAG", "example-22")


class TestRakuten:
    def test_requires_app_id(self, monkeypatch):
        monkeypatch.delenv("RAKUTEN_APP_ID", raising=False)
        ok, reason = RakutenAdapter().available()
        assert ok is False and "RAKUTEN_APP_ID" in reason

    def test_parses_items(self, monkeypatch, rakuten_env):
        payload = {
            "Items": [
                {
                    "Item": {
                        "itemName": "ワイヤレスイヤホン",
                        "itemPrice": 12800,
                        "itemUrl": "https://item.rakuten.co.jp/x/",
                        "shopName": "テストショップ",
                        "postageFlag": 0,
                        "pointRate": 3.0,
                        "availability": 1,
                    }
                }
            ]
        }
        monkeypatch.setattr(
            "saiyasu.platforms.rakuten.httpx.get", lambda *a, **k: FakeResponse(payload)
        )
        offers = RakutenAdapter().search(CTX)
        assert len(offers) == 1
        offer = offers[0]
        assert offer.price == 12800
        assert offer.shipping.kind == "free"  # postageFlag 0 = 送料込み
        assert offer.points[0].rate == pytest.approx(0.03)
        assert offer.points[0].limited is True
        assert offer.source == "api"

    def test_flat_item_shape_is_also_supported(self, monkeypatch, rakuten_env):
        payload = {"Items": [{"itemName": "商品", "itemPrice": 500, "postageFlag": 1}]}
        monkeypatch.setattr(
            "saiyasu.platforms.rakuten.httpx.get", lambda *a, **k: FakeResponse(payload)
        )
        offers = RakutenAdapter().search(CTX)
        assert offers[0].price == 500
        assert offers[0].shipping.kind == "conditional_free"
        assert offers[0].shipping.free_threshold == 3980

    def test_api_error_is_wrapped(self, monkeypatch, rakuten_env):
        payload = {"error": "wrong_parameter", "error_description": "appId is invalid"}
        monkeypatch.setattr(
            "saiyasu.platforms.rakuten.httpx.get", lambda *a, **k: FakeResponse(payload)
        )
        with pytest.raises(AdapterError, match="wrong_parameter"):
            RakutenAdapter().search(CTX)


class TestYahoo:
    def test_parses_hits_and_points(self, monkeypatch, yahoo_env):
        payload = {
            "hits": [
                {
                    "name": "ワイヤレスイヤホン",
                    "price": 13000,
                    "url": "https://store.shopping.yahoo.co.jp/x/",
                    "seller": {"name": "テストストア"},
                    "shipping": {"code": 2, "name": "条件付き送料無料"},
                    "point": {"amount": 130, "times": 1},
                    "inStock": True,
                    "condition": "new",
                }
            ]
        }
        monkeypatch.setattr(
            "saiyasu.platforms.yahoo.httpx.get", lambda *a, **k: FakeResponse(payload)
        )
        offer = YahooAdapter().search(CTX)[0]
        assert offer.price == 13000
        assert offer.shipping.kind == "conditional_free"
        assert offer.points[0].fixed_amount == 130
        assert offer.shop == "テストストア"

    def test_free_shipping_and_used_condition(self, monkeypatch, yahoo_env):
        payload = {
            "hits": [
                {
                    "name": "中古品",
                    "price": 5000,
                    "shipping": {"name": "送料無料"},
                    "condition": "used",
                }
            ]
        }
        monkeypatch.setattr(
            "saiyasu.platforms.yahoo.httpx.get", lambda *a, **k: FakeResponse(payload)
        )
        offer = YahooAdapter().search(CTX)[0]
        assert offer.shipping.kind == "free"
        assert offer.condition == "used"
        assert offer.points[0].rate == pytest.approx(0.01)  # ポイント情報が無ければ基本1%


class TestAmazon:
    def test_signature_headers_are_complete(self, amazon_env):
        headers = AmazonAdapter()._signed_headers('{"Keywords":"x"}')
        assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
        assert "SignedHeaders=content-encoding;content-type;host;x-amz-date;x-amz-target" in headers["Authorization"]
        assert len(headers["Authorization"].split("Signature=")[1]) == 64

    def test_signature_changes_with_the_payload(self, amazon_env):
        adapter = AmazonAdapter()
        a = adapter._signed_headers('{"Keywords":"A"}')
        b = adapter._signed_headers('{"Keywords":"B"}')
        sig = lambda h: h["Authorization"].split("Signature=")[1]
        assert sig(a) != sig(b)

    def test_signature_is_stable_for_the_same_payload_and_timestamp(self, amazon_env):
        adapter = AmazonAdapter()
        a = adapter._signed_headers("{}")
        b = adapter._signed_headers("{}")
        if a["x-amz-date"] != b["x-amz-date"]:
            pytest.skip("署名生成の間に秒が変わった")
        assert a["Authorization"] == b["Authorization"]

    def test_parses_search_result(self, monkeypatch, amazon_env):
        payload = {
            "SearchResult": {
                "Items": [
                    {
                        "ASIN": "B000000000",
                        "DetailPageURL": "https://www.amazon.co.jp/dp/B000000000",
                        "ItemInfo": {"Title": {"DisplayValue": "ワイヤレスイヤホン"}},
                        "Offers": {
                            "Listings": [
                                {
                                    "Price": {"Amount": 12480},
                                    "Condition": {"Value": "New"},
                                    "DeliveryInfo": {
                                        "IsFreeShippingEligible": True,
                                        "IsPrimeEligible": True,
                                    },
                                    "MerchantInfo": {"Name": "Amazon.co.jp"},
                                }
                            ]
                        },
                    }
                ]
            }
        }
        monkeypatch.setattr(
            "saiyasu.platforms.amazon.httpx.post", lambda *a, **k: FakeResponse(payload)
        )
        offer = AmazonAdapter().search(CTX)[0]
        assert offer.price == 12480
        assert offer.shipping.kind == "free"
        assert offer.note == "プライム対象"

    def test_api_errors_are_surfaced(self, monkeypatch, amazon_env):
        payload = {"Errors": [{"Code": "InvalidSignature", "Message": "署名が不正です"}]}
        monkeypatch.setattr(
            "saiyasu.platforms.amazon.httpx.post", lambda *a, **k: FakeResponse(payload)
        )
        with pytest.raises(AdapterError, match="署名が不正です"):
            AmazonAdapter().search(CTX)


class TestManual:
    def test_reads_offers_from_json(self, tmp_path, monkeypatch):
        path = tmp_path / "offers.json"
        path.write_text(
            json.dumps(
                {
                    "kakaku": [
                        {
                            "title": "ワイヤレスイヤホン ABC-1",
                            "price": 11800,
                            "shop": "最安ショップ",
                            "shipping": {"kind": "flat", "fee": 800},
                        },
                        {"title": "まったく別の商品", "price": 100},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("SAIYASU_MANUAL_OFFERS", str(path))

        adapter = ManualAdapter("kakaku", "価格.com")
        ok, message = adapter.available()
        assert ok is True and "2件" in message

        offers = adapter.search(SearchContext(query="ワイヤレスイヤホン", limit=5))
        assert len(offers) == 1  # 検索語に一致するものだけ
        assert offers[0].source == "manual"
        assert offers[0].shipping.fee_for(11800) == 800

    def test_missing_file_is_not_an_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAIYASU_MANUAL_OFFERS", str(tmp_path / "nope.json"))
        adapter = ManualAdapter("mercari", "メルカリ")
        assert adapter.available()[0] is False
        assert adapter.search(CTX) == []

    def test_broken_json_raises_adapter_error(self, monkeypatch, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("SAIYASU_MANUAL_OFFERS", str(path))
        with pytest.raises(AdapterError):
            ManualAdapter("kakaku", "価格.com").search(CTX)


class TestSpec:
    @pytest.mark.parametrize(
        "raw,kind",
        [
            (None, "unknown"),
            (0, "free"),
            (800, "flat"),
            ("送料無料", "free"),
            ({"kind": "free"}, "free"),
            ({"free_threshold": 3980, "fee": 660}, "conditional_free"),
            ({"fee": 500}, "flat"),
        ],
    )
    def test_shipping_shapes(self, raw, kind):
        assert shipping_from_dict(raw).kind == kind

    def test_offer_from_dict_full(self):
        offer = offer_from_dict(
            {
                "title": "商品",
                "price": 5000,
                "coupon": 500,
                "fees": [{"label": "代引き", "amount": 330}],
                "points": [{"label": "P", "rate": 0.05, "limited": True, "cap": 100}],
                "delivery_days": 2,
            },
            platform="x",
            label="X",
        )
        assert offer.coupon == 500
        assert offer.fees[0].amount == 330
        assert offer.points[0].cap == 100 and offer.points[0].limited is True
        assert offer.delivery_days == 2


class TestDemo:
    def test_is_deterministic(self):
        first = demo_offers("イヤホン", "amazon", "Amazon.co.jp")
        second = demo_offers("イヤホン", "amazon", "Amazon.co.jp")
        assert [o.price for o in first] == [o.price for o in second]

    def test_different_queries_differ(self):
        a = demo_offers("イヤホン", "amazon", "Amazon")[0].price
        b = demo_offers("冷蔵庫", "amazon", "Amazon")[0].price
        assert a != b

    def test_marked_as_demo(self):
        offer = demo_offers("イヤホン", "rakuten", "楽天市場")[0]
        assert offer.source == "demo"
        assert "サンプル" in offer.title

    def test_unknown_platform_returns_nothing(self):
        assert demo_offers("イヤホン", "unknown-site", "?") == []
