"""実質価格(送料込み・ポイント還元後)の計算エンジン。

    支払総額 = 商品価格 + 送料 + 手数料 - クーポン
    実質価格 = 支払総額 - 獲得ポイントの円換算価値

「送料無料ライン」があるため、送料はクーポン適用前の商品価格で判定する
(多くのモールが商品代金ベースで判定するため)。
"""

from __future__ import annotations

from .models import Offer, PointLine, PointReward, PriceBreakdown
from .profile import PointProfile


def build_breakdown(offer: Offer, profile: PointProfile | None = None) -> PriceBreakdown:
    """1件の出品について実質価格の内訳を組み立てる。"""
    profile = profile or PointProfile()

    shipping_fee = offer.shipping.fee_for(offer.price, remote=profile.remote_area)
    fee_total = sum(f.amount for f in offer.fees)
    coupon = min(offer.coupon, offer.price)  # クーポンで商品価格以上は引けない

    rewards: list[PointReward] = list(offer.points)
    for label, rate, cap in profile.bonus_rewards(offer.platform):
        rewards.append(PointReward(label=label, rate=rate, cap=cap, limited=True))

    # ポイントはクーポン値引き後の商品価格を基準に付与されるのが一般的
    point_base = max(0, offer.price - coupon)

    lines: list[PointLine] = []
    for reward in rewards:
        amount = reward.amount_for(point_base, shipping_fee)
        if amount <= 0:
            continue
        lines.append(
            PointLine(
                label=reward.label,
                amount=amount,
                limited=reward.limited,
                value_yen=profile.value_of(amount, limited=reward.limited),
            )
        )

    return PriceBreakdown(
        item_price=offer.price,
        shipping_fee=shipping_fee,
        fee_total=fee_total,
        coupon=coupon,
        point_lines=lines,
        shipping_needs_check=offer.shipping.needs_check,
    )


def effective_price(offer: Offer, profile: PointProfile | None = None) -> int:
    """実質価格(円)だけを返すショートカット。"""
    return build_breakdown(offer, profile).effective_price
