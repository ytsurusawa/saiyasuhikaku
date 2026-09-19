"""データモデル。

金額はすべて「円」の整数で扱う。ポイントも「ポイント(=円相当)」の整数。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

# ポイント還元の計算基準
# - "item"              : 商品価格のみが還元対象(多くのモールはこちら)
# - "item_with_shipping": 送料込みの支払額が還元対象(決済側のポイントなど)
PointBasis = Literal["item", "item_with_shipping"]

ShippingKind = Literal["free", "flat", "conditional_free", "unknown"]

Condition = Literal["new", "used", "refurbished"]


@dataclass(frozen=True)
class ShippingPolicy:
    """送料の条件。

    kind:
      free             送料無料(送料込み価格)
      flat             一律 ``fee`` 円
      conditional_free ``free_threshold`` 円以上で無料、未満は ``fee`` 円
      unknown          不明(``fee`` を推定値として使い、要確認フラグを立てる)
    """

    kind: ShippingKind = "unknown"
    fee: int = 0
    free_threshold: int | None = None
    remote_surcharge: int = 0  # 沖縄・離島などの追加送料
    note: str = ""

    @classmethod
    def free(cls, note: str = "送料無料") -> "ShippingPolicy":
        return cls(kind="free", fee=0, note=note)

    @classmethod
    def flat(cls, fee: int, note: str = "") -> "ShippingPolicy":
        return cls(kind="flat", fee=int(fee), note=note or f"一律{int(fee):,}円")

    @classmethod
    def conditional(cls, fee: int, threshold: int, note: str = "") -> "ShippingPolicy":
        return cls(
            kind="conditional_free",
            fee=int(fee),
            free_threshold=int(threshold),
            note=note or f"{int(threshold):,}円以上で無料",
        )

    @classmethod
    def unknown(cls, estimate: int = 0, note: str = "送料は要確認") -> "ShippingPolicy":
        return cls(kind="unknown", fee=int(estimate), note=note)

    @property
    def needs_check(self) -> bool:
        """送料が確定していない(表示上「要確認」にすべき)か。"""
        return self.kind == "unknown"

    def fee_for(self, subtotal: int, *, remote: bool = False) -> int:
        """商品小計 ``subtotal`` 円のときに実際にかかる送料を返す。"""
        if self.kind == "free":
            base = 0
        elif self.kind == "conditional_free":
            threshold = self.free_threshold
            base = 0 if threshold is not None and subtotal >= threshold else self.fee
        else:  # flat / unknown
            base = self.fee
        if base == 0 and self.kind == "free":
            # 「送料無料」は離島も無料として扱う
            return 0
        return base + (self.remote_surcharge if remote else 0)

    def describe(self, subtotal: int, *, remote: bool = False) -> str:
        fee = self.fee_for(subtotal, remote=remote)
        if self.kind == "unknown":
            return f"要確認(推定{fee:,}円)" if fee else "要確認"
        if fee == 0:
            return "無料"
        if self.kind == "conditional_free" and self.free_threshold is not None:
            return f"{fee:,}円(あと{max(0, self.free_threshold - subtotal):,}円で無料)"
        return f"{fee:,}円"


@dataclass(frozen=True)
class PointReward:
    """ポイント還元の1項目(基本ポイント、SPU、キャンペーンなど)。"""

    label: str
    rate: float = 0.0  # 0.01 = 1%
    fixed_amount: int | None = None  # 率ではなく固定ポイントが分かっている場合
    cap: int | None = None  # 1注文あたりの獲得上限ポイント
    basis: PointBasis = "item"
    limited: bool = False  # 期間限定ポイントか(価値を割り引いて評価する)
    note: str = ""

    def amount_for(self, item_price: int, shipping_fee: int) -> int:
        base = item_price if self.basis == "item" else item_price + shipping_fee
        if self.fixed_amount is not None:
            amount = int(self.fixed_amount)
        else:
            amount = int(math.floor(base * self.rate))
        if self.cap is not None:
            amount = min(amount, int(self.cap))
        return max(0, amount)


@dataclass(frozen=True)
class Fee:
    """送料以外の追加費用(代引き手数料、あんしん補償など)。"""

    label: str
    amount: int


@dataclass
class Offer:
    """1つのプラットフォーム/ショップの出品。"""

    platform: str  # "rakuten" などの内部キー
    platform_label: str  # "楽天市場"
    title: str
    price: int  # 税込の商品価格
    url: str = ""
    shop: str = ""
    shipping: ShippingPolicy = field(default_factory=ShippingPolicy.unknown)
    points: list[PointReward] = field(default_factory=list)
    coupon: int = 0  # 即時値引き(クーポン)円
    fees: list[Fee] = field(default_factory=list)
    condition: Condition = "new"
    in_stock: bool = True
    delivery_days: int | None = None
    source: str = "demo"  # "api" | "demo" | "manual"
    note: str = ""

    # --- 商品同定のための識別子（取得できたものだけ） ---
    jan: str | None = None
    model_number: str | None = None

    # --- matching.filter_offers が書き込む判定結果 ---
    match_score: float = 1.0  # 検索語と商品名の一致度（0.0〜1.0）
    suspect_price: bool = False  # 相場から大きく外れた価格か

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "platform_label": self.platform_label,
            "title": self.title,
            "price": self.price,
            "url": self.url,
            "shop": self.shop,
            "condition": self.condition,
            "in_stock": self.in_stock,
            "delivery_days": self.delivery_days,
            "source": self.source,
            "note": self.note,
            "jan": self.jan,
            "model_number": self.model_number,
            "match_score": round(self.match_score, 3),
            "suspect_price": self.suspect_price,
        }


@dataclass(frozen=True)
class PointLine:
    label: str
    amount: int
    limited: bool
    value_yen: int  # 円換算した価値


@dataclass
class PriceBreakdown:
    """実質価格の内訳。

    支払総額   = 商品価格 + 送料 + 手数料 - クーポン
    実質価格   = 支払総額 - 獲得ポイントの円換算価値
    """

    item_price: int
    shipping_fee: int
    fee_total: int
    coupon: int
    point_lines: list[PointLine]
    shipping_needs_check: bool = False

    @property
    def cash_total(self) -> int:
        return self.item_price + self.shipping_fee + self.fee_total - self.coupon

    @property
    def point_total(self) -> int:
        return sum(line.amount for line in self.point_lines)

    @property
    def point_value_yen(self) -> int:
        return sum(line.value_yen for line in self.point_lines)

    @property
    def effective_price(self) -> int:
        return self.cash_total - self.point_value_yen

    @property
    def effective_point_rate(self) -> float:
        """支払総額に対する実質還元率。"""
        return self.point_value_yen / self.cash_total if self.cash_total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_price": self.item_price,
            "shipping_fee": self.shipping_fee,
            "fee_total": self.fee_total,
            "coupon": self.coupon,
            "cash_total": self.cash_total,
            "point_total": self.point_total,
            "point_value_yen": self.point_value_yen,
            "effective_price": self.effective_price,
            "effective_point_rate": round(self.effective_point_rate, 4),
            "shipping_needs_check": self.shipping_needs_check,
            "points": [
                {
                    "label": line.label,
                    "amount": line.amount,
                    "limited": line.limited,
                    "value_yen": line.value_yen,
                }
                for line in self.point_lines
            ],
        }


@dataclass
class RankedOffer:
    """比較結果の1行(出品 + 実質価格の内訳 + 順位)。"""

    rank: int
    offer: Offer
    breakdown: PriceBreakdown
    diff_from_best: int = 0  # 1位との実質価格の差(円、1位は0)

    @property
    def is_best(self) -> bool:
        return self.rank == 1

    def to_dict(self) -> dict[str, Any]:
        data = self.offer.to_dict()
        data.update(
            {
                "rank": self.rank,
                "is_best": self.is_best,
                "diff_from_best": self.diff_from_best,
                "shipping_label": self.offer.shipping.describe(self.offer.price),
                "breakdown": self.breakdown.to_dict(),
            }
        )
        return data


@dataclass
class PlatformStatus:
    """各プラットフォームの取得状況(APIキー未設定・エラーなども表現する)。"""

    platform: str
    label: str
    ok: bool
    offer_count: int = 0
    source: str = "demo"
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "label": self.label,
            "ok": self.ok,
            "offer_count": self.offer_count,
            "source": self.source,
            "message": self.message,
        }


@dataclass
class ComparisonResult:
    """一括比較の結果一式。"""

    query: str
    ranked: list[RankedOffer]
    statuses: list[PlatformStatus]
    profile_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    #: 商品同定の結果（matching.MatchReport）。除外した出品の内訳を持つ。
    match_report: Any = None

    @property
    def best(self) -> RankedOffer | None:
        return self.ranked[0] if self.ranked else None

    @property
    def cheapest_sticker(self) -> RankedOffer | None:
        """商品価格(表示価格)だけで見たときの最安。"""
        if not self.ranked:
            return None
        return min(self.ranked, key=lambda r: r.offer.price)

    def savings_vs_worst(self) -> int:
        if len(self.ranked) < 2:
            return 0
        return self.ranked[-1].breakdown.effective_price - self.ranked[0].breakdown.effective_price

    def to_dict(self) -> dict[str, Any]:
        best = self.best
        sticker = self.cheapest_sticker
        return {
            "query": self.query,
            "count": len(self.ranked),
            "best": best.to_dict() if best else None,
            "verdict": self.verdict(),
            "results": [r.to_dict() for r in self.ranked],
            "statuses": [s.to_dict() for s in self.statuses],
            "profile": self.profile_summary,
            "warnings": self.warnings,
            "sticker_cheapest_platform": sticker.offer.platform_label if sticker else None,
            "savings_vs_worst": self.savings_vs_worst(),
            "matching": self.match_report.to_dict() if self.match_report else None,
        }

    def verdict(self) -> str:
        """「結局どこが一番お得か」を1〜2文で説明する。"""
        best = self.best
        if best is None:
            return "比較できる出品が見つかりませんでした。"
        b = best.breakdown
        parts = [
            f"最もお得なのは【{best.offer.platform_label}】の実質 {b.effective_price:,}円"
            f"(支払 {b.cash_total:,}円 − ポイント {b.point_value_yen:,}円相当)です。"
        ]
        if len(self.ranked) >= 2:
            second = self.ranked[1]
            parts.append(
                f"2位の{second.offer.platform_label}より {second.diff_from_best:,}円お得。"
            )
        sticker = self.cheapest_sticker
        if sticker is not None and sticker.offer.platform != best.offer.platform:
            parts.append(
                f"※表示価格だけなら{sticker.offer.platform_label}が最安ですが、"
                f"送料とポイントを入れると順位が逆転します。"
            )
        if any(r.breakdown.shipping_needs_check for r in self.ranked[:3]):
            parts.append("※上位に送料が確定していない出品があります。購入前にご確認ください。")
        if best.offer.suspect_price:
            parts.append(
                "※この出品は価格が相場から大きく外れています。"
                "同一商品かどうか（付属品のみ・並行輸入品でないか）を必ずご確認ください。"
            )
        return " ".join(parts)
