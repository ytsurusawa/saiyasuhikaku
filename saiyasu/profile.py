"""ユーザーのポイント還元条件。

同じ商品でも「楽天SPUが何倍か」「LYPプレミアム会員か」「PayPayの還元ステップ」
などで実質価格は大きく変わる。ここではその条件をまとめて持ち、
プラットフォームごとの「上乗せ還元率」に変換する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 楽天の買い回り(お買い物マラソン)は最大+9%
RAKUTEN_KAIMAWARI_MAX_RATE = 0.09


@dataclass
class PointProfile:
    """ポイント還元まわりのユーザー設定。

    ``point_value`` / ``limited_point_value`` は「1ポイントを何円の価値として
    評価するか」。期間限定ポイントは使い道が限られるため既定では 0.9 円で評価する。
    """

    # --- ポイントの価値 ---
    point_value: float = 1.0
    limited_point_value: float = 0.9

    # --- 楽天市場 ---
    rakuten_spu_rate: float = 0.0  # SPUの上乗せ分(0.04 = +4%)
    rakuten_kaimawari_shops: int = 0  # 買い回りの購入店舗数(n店舗で+(n-1)%)
    rakuten_point_cap: int | None = None  # キャンペーンポイントの獲得上限

    # --- Yahoo!ショッピング / PayPay ---
    lyp_premium: bool = False  # LYPプレミアム会員(+2%相当)
    yahoo_day_campaign: bool = False  # 5のつく日など(+4%相当)
    paypay_step_rate: float = 0.0  # PayPayステップ等の上乗せ

    # --- Amazon ---
    amazon_prime: bool = False
    amazon_card_rate: float = 0.0  # Amazon Mastercard などの還元率

    # --- その他モール共通の上乗せ(任意) ---
    extra_bonus_rates: dict[str, float] = field(default_factory=dict)

    # --- 配送条件 ---
    remote_area: bool = False  # 沖縄・離島など追加送料がかかる地域か

    # --- 比較条件 ---
    include_used: bool = False  # 中古・リファービッシュも比較対象に含めるか

    # ------------------------------------------------------------------
    def bonus_rewards(self, platform: str) -> list[tuple[str, float, int | None]]:
        """プラットフォーム固有の上乗せ還元を ``(ラベル, 率, 上限)`` で返す。

        ここで返るのは「ユーザー条件による上乗せ」だけで、
        出品側の基本ポイントはアダプタ側が付与する。
        """
        out: list[tuple[str, float, int | None]] = []

        if platform == "rakuten":
            if self.rakuten_spu_rate > 0:
                out.append(("SPU上乗せ", self.rakuten_spu_rate, self.rakuten_point_cap))
            if self.rakuten_kaimawari_shops >= 2:
                rate = min(
                    (self.rakuten_kaimawari_shops - 1) / 100.0,
                    RAKUTEN_KAIMAWARI_MAX_RATE,
                )
                out.append(
                    (f"買い回り{self.rakuten_kaimawari_shops}店舗", rate, self.rakuten_point_cap)
                )
        elif platform == "yahoo":
            if self.lyp_premium:
                out.append(("LYPプレミアム", 0.02, None))
            if self.yahoo_day_campaign:
                out.append(("5のつく日など", 0.04, None))
            if self.paypay_step_rate > 0:
                out.append(("PayPayステップ", self.paypay_step_rate, None))
        elif platform == "amazon":
            if self.amazon_card_rate > 0:
                out.append(("Amazonカード", self.amazon_card_rate, None))

        extra = self.extra_bonus_rates.get(platform, 0.0)
        if extra:
            out.append(("追加還元", extra, None))
        return out

    def value_of(self, points: int, *, limited: bool) -> int:
        """ポイントを円換算した価値。"""
        rate = self.limited_point_value if limited else self.point_value
        return int(round(points * rate))

    # ------------------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        return {
            "point_value": self.point_value,
            "limited_point_value": self.limited_point_value,
            "rakuten_spu_rate": self.rakuten_spu_rate,
            "rakuten_kaimawari_shops": self.rakuten_kaimawari_shops,
            "lyp_premium": self.lyp_premium,
            "yahoo_day_campaign": self.yahoo_day_campaign,
            "paypay_step_rate": self.paypay_step_rate,
            "amazon_prime": self.amazon_prime,
            "amazon_card_rate": self.amazon_card_rate,
            "remote_area": self.remote_area,
            "include_used": self.include_used,
            "extra_bonus_rates": dict(self.extra_bonus_rates),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PointProfile":
        data = dict(data or {})
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
