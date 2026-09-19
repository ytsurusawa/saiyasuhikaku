"""実質価格の計算ロジックのテスト。"""

from saiyasu.models import Fee, Offer, PointReward, ShippingPolicy
from saiyasu.pricing import build_breakdown, effective_price
from saiyasu.profile import PointProfile


def offer(**kwargs) -> Offer:
    base = dict(
        platform="test",
        platform_label="テスト",
        title="テスト商品",
        price=10000,
        shipping=ShippingPolicy.free(),
    )
    base.update(kwargs)
    return Offer(**base)


class TestShippingPolicy:
    def test_free_is_always_zero(self):
        assert ShippingPolicy.free().fee_for(100) == 0

    def test_flat_fee_applies_regardless_of_subtotal(self):
        policy = ShippingPolicy.flat(800)
        assert policy.fee_for(100) == 800
        assert policy.fee_for(100000) == 800

    def test_conditional_free_crosses_threshold(self):
        policy = ShippingPolicy.conditional(660, 3980)
        assert policy.fee_for(3979) == 660
        assert policy.fee_for(3980) == 0

    def test_remote_surcharge_added_when_fee_applies(self):
        policy = ShippingPolicy(kind="flat", fee=660, remote_surcharge=1200)
        assert policy.fee_for(1000) == 660
        assert policy.fee_for(1000, remote=True) == 1860

    def test_free_shipping_ignores_remote_surcharge(self):
        assert ShippingPolicy.free().fee_for(1000, remote=True) == 0

    def test_unknown_is_flagged_for_review(self):
        assert ShippingPolicy.unknown(500).needs_check is True
        assert ShippingPolicy.free().needs_check is False

    def test_describe_shows_remaining_amount_to_free(self):
        assert "あと980円" in ShippingPolicy.conditional(660, 3980).describe(3000)


class TestPointReward:
    def test_rate_is_floored(self):
        assert PointReward("p", rate=0.01).amount_for(1999, 0) == 19

    def test_cap_limits_the_award(self):
        assert PointReward("p", rate=0.10, cap=1000).amount_for(50000, 0) == 1000

    def test_fixed_amount_wins_over_rate(self):
        assert PointReward("p", rate=0.5, fixed_amount=77).amount_for(10000, 0) == 77

    def test_basis_can_include_shipping(self):
        reward = PointReward("p", rate=0.01, basis="item_with_shipping")
        assert reward.amount_for(10000, 500) == 105


class TestBreakdown:
    def test_shipping_free_line_uses_item_price(self):
        b = build_breakdown(offer(price=4000, shipping=ShippingPolicy.conditional(660, 3980)))
        assert b.shipping_fee == 0

    def test_cash_total_sums_everything(self):
        b = build_breakdown(
            offer(
                price=10000,
                shipping=ShippingPolicy.flat(660),
                fees=[Fee("代引き手数料", 330)],
                coupon=500,
            )
        )
        assert b.cash_total == 10000 + 660 + 330 - 500

    def test_effective_price_subtracts_point_value(self):
        b = build_breakdown(
            offer(points=[PointReward("基本", rate=0.01)]),
            PointProfile(point_value=1.0),
        )
        assert b.point_total == 100
        assert b.effective_price == 10000 - 100

    def test_limited_points_are_discounted(self):
        b = build_breakdown(
            offer(points=[PointReward("期間限定", rate=0.10, limited=True)]),
            PointProfile(limited_point_value=0.8),
        )
        assert b.point_total == 1000
        assert b.point_value_yen == 800
        assert b.effective_price == 9200

    def test_coupon_reduces_the_point_base(self):
        b = build_breakdown(offer(coupon=5000, points=[PointReward("基本", rate=0.01)]))
        assert b.point_total == 50  # 10,000ではなく5,000円が基準

    def test_coupon_cannot_exceed_item_price(self):
        b = build_breakdown(offer(price=1000, coupon=99999))
        assert b.coupon == 1000
        assert b.cash_total == 0

    def test_profile_bonus_rates_are_added(self):
        o = offer(platform="rakuten", points=[PointReward("基本", rate=0.01)])
        b = build_breakdown(o, PointProfile(rakuten_spu_rate=0.04, limited_point_value=1.0))
        assert b.point_total == 100 + 400

    def test_kaimawari_is_capped_at_nine_percent(self):
        o = offer(platform="rakuten", price=100000)
        b = build_breakdown(
            o, PointProfile(rakuten_kaimawari_shops=20, limited_point_value=1.0)
        )
        assert b.point_total == 9000

    def test_remote_area_raises_effective_price(self):
        o = offer(shipping=ShippingPolicy(kind="flat", fee=660, remote_surcharge=1000))
        assert effective_price(o, PointProfile(remote_area=True)) - effective_price(o) == 1000

    def test_effective_point_rate(self):
        b = build_breakdown(
            offer(points=[PointReward("基本", rate=0.10)]), PointProfile(point_value=1.0)
        )
        assert round(b.effective_point_rate, 3) == 0.1

    def test_zero_cash_total_does_not_divide_by_zero(self):
        assert build_breakdown(offer(price=1000, coupon=1000)).effective_point_rate == 0.0
