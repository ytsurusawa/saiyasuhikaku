"""デモ(サンプル)データ生成。

APIキーが未設定でも機能をひととおり試せるように、検索語から決定的に
「それっぽい」価格を組み立てる。実在の価格ではないため ``source="demo"`` を
付け、UI・CLIでは必ずサンプルである旨を表示する。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from ..matching import is_accessory
from ..models import Offer
from .base import PlatformAdapter, SearchContext
from .spec import offer_from_dict


@dataclass(frozen=True)
class DemoProfile:
    """プラットフォームごとの価格傾向と送料・ポイントの型。"""

    price_ratio: float
    shop: str
    shipping: dict[str, Any]
    points: list[dict[str, Any]]
    coupon_rate: float = 0.0
    condition: str = "new"
    delivery_days: int = 3
    note: str = ""


DEMO_PROFILES: dict[str, DemoProfile] = {
    "amazon": DemoProfile(
        price_ratio=1.00,
        shop="Amazon.co.jp",
        shipping={"kind": "conditional_free", "fee": 460, "free_threshold": 2000},
        points=[{"label": "Amazonポイント", "rate": 0.01}],
        delivery_days=1,
    ),
    "rakuten": DemoProfile(
        price_ratio=1.04,
        shop="楽天ブックス",
        shipping={"kind": "free", "note": "送料込み"},
        points=[
            {"label": "楽天ポイント(基本1倍)", "rate": 0.01},
            {"label": "ショップ独自ポイント2倍", "rate": 0.02, "limited": True},
        ],
        delivery_days=3,
    ),
    "yahoo": DemoProfile(
        price_ratio=1.05,
        shop="PayPayモール系ストア",
        shipping={"kind": "conditional_free", "fee": 660, "free_threshold": 3980},
        points=[
            {"label": "PayPayポイント(基本1%)", "rate": 0.01},
            {"label": "ストアポイント", "rate": 0.01, "limited": True},
        ],
        delivery_days=3,
    ),
    "kakaku": DemoProfile(
        price_ratio=0.94,
        shop="価格.com掲載の最安ショップ",
        shipping={"kind": "flat", "fee": 800, "note": "ショップ個別送料(推定)"},
        points=[],
        delivery_days=5,
        note="最安ショップは送料・保証条件が異なる場合あり",
    ),
    "yodobashi": DemoProfile(
        price_ratio=1.02,
        shop="ヨドバシ.com",
        shipping={"kind": "free", "note": "全国送料無料"},
        points=[{"label": "ゴールドポイント10%", "rate": 0.10}],
        delivery_days=1,
    ),
    "biccamera": DemoProfile(
        price_ratio=1.02,
        shop="ビックカメラ.com",
        shipping={"kind": "conditional_free", "fee": 500, "free_threshold": 2000},
        points=[{"label": "ビックポイント10%", "rate": 0.10}],
        delivery_days=2,
    ),
    "aupay": DemoProfile(
        price_ratio=1.06,
        shop="au PAY マーケット出店ストア",
        shipping={"kind": "conditional_free", "fee": 660, "free_threshold": 3980},
        points=[
            {"label": "Pontaポイント(基本1%)", "rate": 0.01},
            {"label": "お買い得市キャンペーン", "rate": 0.05, "limited": True, "cap": 3000},
        ],
        delivery_days=4,
    ),
    "qoo10": DemoProfile(
        price_ratio=1.00,
        shop="Qoo10出店ショップ",
        shipping={"kind": "free", "note": "送料込み表示が多い"},
        points=[],
        coupon_rate=0.10,
        delivery_days=7,
        note="メガ割クーポン(20%前後)適用時はさらに安くなる",
    ),
    "mercari": DemoProfile(
        price_ratio=0.72,
        shop="メルカリ出品者",
        shipping={"kind": "free", "note": "送料込み出品"},
        points=[],
        condition="used",
        delivery_days=4,
        note="中古のため状態・保証は要確認",
    ),
}


def _jitter(query: str, platform: str) -> float:
    """検索語とプラットフォームから決定的な ±3% のばらつきを作る。"""
    digest = hashlib.sha256(f"{query}|{platform}".encode("utf-8")).hexdigest()
    return 1.0 + ((int(digest[:8], 16) % 61) - 30) / 1000.0


def base_price(query: str) -> int:
    """検索語から決定的に基準価格(3,000〜60,000円)を決める。"""
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return 3000 + (int(digest[8:16], 16) % 57) * 1000


#: モール型(出店者が自由に出品する)サイト。互換アクセサリが紛れ込みやすい。
MARKETPLACES = ("rakuten", "yahoo", "aupay", "qoo10")


def _accessory_trap(query: str, platform: str, label: str) -> Offer | None:
    """商品同定の動作確認用に、アクセサリ出品をサンプルへ1件混ぜる。

    実際のモール検索でも「本体を探したのに互換ケースが並ぶ」ことは頻繁に起きる。
    絞り込みが効いていることを画面で確認できるよう、デモにも同じ状況を再現する。
    検索語自体がアクセサリを指している場合は混ぜない。
    """
    if platform not in MARKETPLACES:
        return None
    if is_accessory(query, f"{query} 保護ケース") is None:
        return None  # 検索語にアクセサリ語が含まれる場合は本物なので混ぜない
    price = max(880, int(base_price(query) * 0.04 / 10) * 10)
    return offer_from_dict(
        {
            "title": f"{query} 用 保護ケース（サンプルデータ）",
            "price": price,
            "shop": "アクセサリ専門ストア",
            "shipping": {"kind": "free"},
            "points": [],
            "delivery_days": 5,
            "note": "本体ではありません",
        },
        platform=platform,
        label=label,
        source="demo",
    )


def demo_offers(query: str, platform: str, label: str, limit: int = 1) -> list[Offer]:
    """指定プラットフォームのサンプル出品を作る。"""
    profile = DEMO_PROFILES.get(platform)
    if profile is None:
        return []

    offers: list[Offer] = []
    for index in range(max(1, limit)):
        ratio = profile.price_ratio * _jitter(f"{query}#{index}", platform)
        price = int(round(base_price(query) * ratio * (1 + 0.04 * index) / 10) * 10)
        data: dict[str, Any] = {
            "title": f"{query}(サンプルデータ)",
            "price": price,
            "shop": profile.shop if index == 0 else f"{profile.shop} 他店",
            "url": "",
            "shipping": profile.shipping,
            "points": profile.points,
            "coupon": int(price * profile.coupon_rate),
            "condition": profile.condition,
            "delivery_days": profile.delivery_days,
            "note": profile.note,
        }
        offers.append(offer_from_dict(data, platform=platform, label=label, source="demo"))

    trap = _accessory_trap(query, platform, label)
    if trap is not None:
        offers.append(trap)
    return offers


class DemoAdapter(PlatformAdapter):
    """デモ専用アダプタ(テストや ``--demo`` 実行で使う)。"""

    def __init__(self, key: str, label: str) -> None:
        self.key = key
        self.label = label

    def available(self) -> tuple[bool, str]:
        return True, "デモデータ"

    def search(self, ctx: SearchContext) -> list[Offer]:
        return demo_offers(ctx.query, self.key, self.label, limit=ctx.limit)
