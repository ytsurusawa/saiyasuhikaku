"""商品同定（別商品の混入防止）のテスト。"""

import pytest

from saiyasu.comparator import Comparator
from saiyasu.matching import (
    extract_models,
    filter_offers,
    is_accessory,
    normalize,
    title_score,
)
from saiyasu.models import Offer, ShippingPolicy
from saiyasu.platforms import PlatformAdapter, SearchContext


def make(title, *, platform="x", label="X", price=10000, jan=None, condition="new", model=None):
    return Offer(
        platform=platform,
        platform_label=label,
        title=title,
        price=price,
        shipping=ShippingPolicy.free(),
        jan=jan,
        model_number=model,
        condition=condition,
    )


class TestNormalize:
    def test_full_width_is_folded_to_half_width(self):
        assert normalize("ＳＯＮＹ　ＷＨ－１０００ＸＭ５") == "sony wh-1000xm5"

    def test_punctuation_becomes_separators(self):
        assert normalize("Anker(アンカー)/充電器") == "anker アンカー 充電器"


class TestExtractModels:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("ソニー WH-1000XM5 ヘッドホン", {"wh1000xm5"}),
            ("ＷＨ－１０００ＸＭ５", {"wh1000xm5"}),
            ("Anker A2637 充電器", {"a2637"}),
            ("ただの日本語の商品名", set()),
            ("10000mAh", {"10000mah"}),
        ],
    )
    def test_extraction(self, text, expected):
        assert extract_models(text) == expected

    def test_full_width_and_half_width_match(self):
        assert extract_models("ＷＨ－１０００ＸＭ５") & extract_models("wh-1000xm5")


class TestTitleScore:
    def test_exact_match(self):
        assert title_score("Anker PowerCore 10000", "Anker PowerCore 10000 モバイルバッテリー") == 1.0

    def test_unrelated_product(self):
        assert title_score("Anker PowerCore 10000", "エレコム 5000mAh") == 0.0

    def test_partial_match(self):
        assert title_score("ソニー ヘッドホン 黒", "ソニー ヘッドホン") == pytest.approx(2 / 3)

    def test_empty_query_matches_everything(self):
        assert title_score("", "なんでも") == 1.0


class TestAccessoryDetection:
    def test_case_is_detected_as_accessory(self):
        assert is_accessory("WH-1000XM5", "WH-1000XM5 用 保護ケース") == "ケース"

    def test_not_an_accessory_when_the_user_wants_one(self):
        assert is_accessory("WH-1000XM5 ケース", "WH-1000XM5 用 ケース") is None

    def test_plain_product_is_not_an_accessory(self):
        assert is_accessory("WH-1000XM5", "ソニー WH-1000XM5 ヘッドホン") is None


class TestFilterOffers:
    def test_accessory_is_excluded(self):
        """互換ケースが本体と一緒に並ばないこと（この機能の主目的）。"""
        body = make("ソニー WH-1000XM5 ヘッドホン", price=48000)
        case = make("WH-1000XM5 専用 保護ケース", price=1980)
        report = filter_offers("WH-1000XM5", [body, case])

        assert report.kept == [body]
        assert len(report.excluded) == 1
        assert report.excluded[0].reason == "accessory"
        assert "アクセサリ" in report.excluded[0].reason_label

    def test_model_number_mismatch_is_excluded(self):
        right = make("ソニー WH-1000XM5", price=48000)
        wrong = make("ソニー WH-1000XM4", price=38000)
        report = filter_offers("WH-1000XM5", [right, wrong])

        assert report.kept == [right]
        assert report.excluded[0].reason == "model"

    def test_jan_mismatch_is_excluded(self):
        a = make("ソニー WH-1000XM5 ブラック", jan="4548736134560")
        b = make("ソニー WH-1000XM5 シルバー", jan="4548736134577")
        c = make("ソニー WH-1000XM5 ブラック 並行輸入", jan="4548736134560")
        report = filter_offers("WH-1000XM5", [a, b, c])

        assert report.reference_jan == "4548736134560"
        assert report.kept == [a, c]
        assert report.excluded[0].reason == "jan"

    def test_offers_without_jan_are_kept(self):
        """JANを返さないモール（楽天など）の出品を巻き添えで落とさない。"""
        with_jan = make("ソニー WH-1000XM5", jan="4548736134560")
        without = make("ソニー WH-1000XM5 楽天市場店")
        report = filter_offers("WH-1000XM5", [with_jan, without])
        assert report.kept == [with_jan, without]

    def test_unrelated_title_is_excluded_by_score(self):
        good = make("Anker PowerCore 10000 モバイルバッテリー")
        bad = make("エレコム モバイルバッテリー 5000mAh")
        report = filter_offers("Anker PowerCore 10000", [good, bad])
        assert report.kept == [good]
        assert report.excluded[0].reason == "title"

    def test_strict_false_keeps_everything(self):
        body = make("ソニー WH-1000XM5")
        case = make("WH-1000XM5 保護ケース")
        report = filter_offers("WH-1000XM5", [body, case], strict=False)
        assert len(report.kept) == 2
        assert report.excluded == []

    def test_match_score_is_recorded_on_the_offer(self):
        offer = make("Anker PowerCore 10000 モバイルバッテリー")
        filter_offers("Anker PowerCore 10000", [offer], strict=False)
        assert offer.match_score == 1.0

    def test_empty_input(self):
        report = filter_offers("何か", [])
        assert report.kept == [] and report.excluded == []

    def test_warnings_summarize_exclusions(self):
        report = filter_offers(
            "WH-1000XM5",
            [make("ソニー WH-1000XM5"), make("WH-1000XM5 ケース"), make("WH-1000XM5 カバー")],
        )
        text = " ".join(report.warnings())
        assert "2件を比較から除外" in text


class TestPriceOutliers:
    def test_absurdly_cheap_offer_is_flagged_not_dropped(self):
        offers = [
            make("ソニー WH-1000XM5", price=48000),
            make("ソニー WH-1000XM5", price=47000),
            make("ソニー WH-1000XM5", price=49000),
            make("ソニー WH-1000XM5 (箱のみ)", price=2000),
        ]
        report = filter_offers("WH-1000XM5", offers)
        cheap = offers[-1]
        assert cheap in report.kept  # 掘り出し物の可能性があるため除外しない
        assert cheap.suspect_price is True
        assert any("相場から大きく外れ" in w for w in report.warnings())

    def test_normal_spread_is_not_flagged(self):
        offers = [make("ソニー WH-1000XM5", price=p) for p in (45000, 48000, 52000)]
        report = filter_offers("WH-1000XM5", offers)
        assert not any(o.suspect_price for o in report.kept)

    def test_used_items_are_not_flagged_for_being_cheap(self):
        offers = [
            make("ソニー WH-1000XM5", price=48000),
            make("ソニー WH-1000XM5", price=47000),
            make("ソニー WH-1000XM5", price=49000),
            make("ソニー WH-1000XM5 中古", price=12000, condition="used"),
        ]
        report = filter_offers("WH-1000XM5", offers)
        assert not any(o.suspect_price for o in report.kept)

    def test_too_few_offers_to_judge(self):
        offers = [make("商品", price=1000), make("商品", price=90000)]
        report = filter_offers("商品", offers)
        assert not any(o.suspect_price for o in report.kept)


class StubAdapter(PlatformAdapter):
    def __init__(self, key, label, offers):
        self.key, self.label, self._offers = key, label, offers

    def available(self):
        return True, ""

    def search(self, ctx: SearchContext):
        return list(self._offers)


class TestComparatorIntegration:
    def test_accessory_never_wins_the_comparison(self):
        """アクセサリが「最安」として1位に出てしまわないこと。"""
        comparator = Comparator(
            [
                StubAdapter(
                    "amazon",
                    "Amazon",
                    [make("ソニー WH-1000XM5 ヘッドホン", price=48000, platform="amazon")],
                ),
                StubAdapter(
                    "rakuten",
                    "楽天市場",
                    [make("WH-1000XM5 専用 ケース", price=1500, platform="rakuten")],
                ),
            ],
            allow_demo=False,
        )
        result = comparator.compare("WH-1000XM5")

        assert len(result.ranked) == 1
        assert result.best.offer.platform == "amazon"
        assert result.match_report.excluded_count == 1

    def test_exclusions_appear_in_the_api_payload(self):
        comparator = Comparator(
            [StubAdapter("a", "A", [make("ソニー WH-1000XM5"), make("WH-1000XM5 ケース")])],
            allow_demo=False,
        )
        data = comparator.compare("WH-1000XM5").to_dict()
        assert data["matching"]["excluded_count"] == 1
        assert data["matching"]["excluded"][0]["reason"] == "accessory"

    def test_strict_matching_can_be_disabled(self):
        comparator = Comparator(
            [
                StubAdapter(
                    "a",
                    "A",
                    [
                        make("ソニー WH-1000XM5", platform="a"),
                        make("WH-1000XM5 ケース", price=1500, platform="b"),
                    ],
                )
            ],
            allow_demo=False,
        )
        result = comparator.compare("WH-1000XM5", strict_matching=False)
        assert len(result.ranked) == 2

    def test_all_excluded_gives_a_helpful_warning(self):
        comparator = Comparator(
            [StubAdapter("a", "A", [make("まったく別の商品")])], allow_demo=False
        )
        result = comparator.compare("WH-1000XM5")
        assert result.ranked == []
        assert any("型番まで含めた" in w for w in result.warnings)

    def test_suspect_price_is_called_out_in_the_verdict(self):
        offers = [make(f"ソニー WH-1000XM5 {i}", price=p) for i, p in enumerate((48000, 47000, 49000))]
        offers.append(make("ソニー WH-1000XM5 箱のみ", price=1500))
        comparator = Comparator([StubAdapter("a", "A", offers)], allow_demo=False)
        result = comparator.compare("WH-1000XM5", per_platform=5)
        assert result.best.offer.suspect_price is True
        assert "相場から大きく外れ" in result.verdict()
