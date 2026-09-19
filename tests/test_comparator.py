"""比較・ランキングのテスト。"""

import pytest

from saiyasu.comparator import Comparator
from saiyasu.models import Offer, PointReward, ShippingPolicy
from saiyasu.platforms import AdapterError, PlatformAdapter, SearchContext
from saiyasu.profile import PointProfile


class StubAdapter(PlatformAdapter):
    def __init__(self, key, label, offers, *, fail=False):
        self.key, self.label, self._offers, self._fail = key, label, offers, fail

    def available(self):
        return True, ""

    def search(self, ctx: SearchContext):
        if self._fail:
            raise AdapterError("接続エラー")
        return list(self._offers)


def make(platform, label, price, shipping, points=(), **kwargs):
    return Offer(
        platform=platform,
        platform_label=label,
        title=f"{label}の商品",
        price=price,
        shipping=shipping,
        points=list(points),
        **kwargs,
    )


class TestRanking:
    def test_cheapest_sticker_price_can_lose_on_effective_price(self):
        """表示価格が最安でも、送料とポイントで順位が逆転する。"""
        cheap = make("kakaku", "価格.com", 10000, ShippingPolicy.flat(1500))
        rich = make(
            "yodobashi", "ヨドバシ.com", 10500, ShippingPolicy.free(),
            [PointReward("ゴールドポイント", rate=0.10)],
        )
        ranked = Comparator([]).rank([cheap, rich], profile=PointProfile(point_value=1.0))

        assert ranked[0].offer.platform == "yodobashi"  # 実質 9,450円
        assert ranked[0].breakdown.effective_price == 9450
        assert ranked[1].breakdown.effective_price == 11500
        assert ranked[1].diff_from_best == 2050

    def test_best_flag_and_ranks_are_sequential(self):
        offers = [
            make("a", "A", 1000, ShippingPolicy.free()),
            make("b", "B", 2000, ShippingPolicy.free()),
            make("c", "C", 3000, ShippingPolicy.free()),
        ]
        ranked = Comparator([]).rank(offers)
        assert [r.rank for r in ranked] == [1, 2, 3]
        assert ranked[0].is_best and not ranked[1].is_best

    def test_per_platform_limits_rows_per_site(self):
        offers = [make("a", "A", p, ShippingPolicy.free()) for p in (1000, 1100, 1200)]
        assert len(Comparator([]).rank(offers, per_platform=1)) == 1
        assert len(Comparator([]).rank(offers, per_platform=2)) == 2

    def test_used_offers_excluded_by_default(self):
        used = make("mercari", "メルカリ", 500, ShippingPolicy.free(), condition="used")
        new = make("amazon", "Amazon", 5000, ShippingPolicy.free())
        assert [r.offer.platform for r in Comparator([]).rank([used, new])] == ["amazon"]

        with_used = Comparator([]).rank([used, new], profile=PointProfile(include_used=True))
        assert with_used[0].offer.platform == "mercari"

    def test_out_of_stock_and_zero_price_are_dropped(self):
        offers = [
            make("a", "A", 1000, ShippingPolicy.free(), in_stock=False),
            make("b", "B", 0, ShippingPolicy.free()),
            make("c", "C", 2000, ShippingPolicy.free()),
        ]
        assert [r.offer.platform for r in Comparator([]).rank(offers)] == ["c"]

    def test_tie_is_broken_by_delivery_speed(self):
        slow = make("a", "A", 1000, ShippingPolicy.free(), delivery_days=7)
        fast = make("b", "B", 1000, ShippingPolicy.free(), delivery_days=1)
        assert Comparator([]).rank([slow, fast])[0].offer.platform == "b"

    def test_empty_input(self):
        assert Comparator([]).rank([]) == []


class TestCompare:
    def test_collects_from_every_adapter(self):
        comparator = Comparator(
            [
                StubAdapter("a", "A", [make("a", "A", 3000, ShippingPolicy.free())]),
                StubAdapter("b", "B", [make("b", "B", 2000, ShippingPolicy.free())]),
            ],
            allow_demo=False,
        )
        result = comparator.compare("テスト")
        assert len(result.ranked) == 2
        assert result.best.offer.platform == "b"
        assert all(s.ok for s in result.statuses)

    def test_adapter_failure_does_not_break_the_comparison(self):
        comparator = Comparator(
            [
                StubAdapter("a", "A", [], fail=True),
                StubAdapter("b", "B", [make("b", "B", 2000, ShippingPolicy.free())]),
            ],
            allow_demo=False,
        )
        result = comparator.compare("テスト")
        assert len(result.ranked) == 1
        failed = next(s for s in result.statuses if s.platform == "a")
        assert failed.ok is False and "接続エラー" in failed.message

    def test_demo_fallback_marks_the_source(self):
        comparator = Comparator([StubAdapter("amazon", "Amazon", [], fail=True)], allow_demo=True)
        result = comparator.compare("イヤホン")
        assert result.statuses[0].source == "demo"
        assert result.ranked and result.ranked[0].offer.source == "demo"
        assert any("サンプル" in w for w in result.warnings)

    def test_platform_filter(self):
        comparator = Comparator(
            [
                StubAdapter("a", "A", [make("a", "A", 3000, ShippingPolicy.free())]),
                StubAdapter("b", "B", [make("b", "B", 2000, ShippingPolicy.free())]),
            ],
            allow_demo=False,
        )
        result = comparator.compare("テスト", platforms=["a"])
        assert [s.platform for s in result.statuses] == ["a"]

    def test_blank_query_returns_a_warning(self):
        result = Comparator([]).compare("   ")
        assert result.ranked == []
        assert "商品名" in result.warnings[0]


class TestVerdict:
    def test_verdict_names_the_winner_and_the_gap(self):
        comparator = Comparator([], allow_demo=False)
        offers = [
            make("yodobashi", "ヨドバシ.com", 10500, ShippingPolicy.free(),
                 [PointReward("ゴールドポイント", rate=0.10)]),
            make("kakaku", "価格.com", 10000, ShippingPolicy.flat(1500)),
        ]
        result = comparator.compare("x", platforms=[])
        result.ranked = comparator.rank(offers, profile=PointProfile(point_value=1.0))
        text = result.verdict()
        assert "ヨドバシ.com" in text and "9,450円" in text
        assert "価格.comが最安" in text  # 表示価格の逆転を明示する

    def test_savings_vs_worst(self):
        comparator = Comparator([], allow_demo=False)
        result = comparator.compare("x", platforms=[])
        result.ranked = comparator.rank(
            [
                make("a", "A", 1000, ShippingPolicy.free()),
                make("b", "B", 4000, ShippingPolicy.free()),
            ]
        )
        assert result.savings_vs_worst() == 3000

    def test_empty_result_verdict(self):
        assert "見つかりません" in Comparator([]).compare("x", platforms=[]).verdict()
