"""Yahoo!ショッピングアダプタ(Yahoo!ショッピング商品検索API v3)。

必要な環境変数:
  YAHOO_APP_ID  Yahoo!デベロッパーネットワークのアプリケーションID(Client ID)
"""

from __future__ import annotations

from typing import Any

import httpx

from ..models import Offer, PointReward, ShippingPolicy
from .base import AdapterError, PlatformAdapter, SearchContext

ENDPOINT = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"

# 条件付き送料無料の出品に使う推定値
ASSUMED_SHIPPING_FEE = 660
ASSUMED_FREE_LINE = 3980


class YahooAdapter(PlatformAdapter):
    key = "yahoo"
    label = "Yahoo!ショッピング"
    required_env = ("YAHOO_APP_ID",)

    def search(self, ctx: SearchContext) -> list[Offer]:
        params: dict[str, Any] = {
            "appid": self.env("YAHOO_APP_ID"),
            "query": ctx.query,
            "results": max(1, min(ctx.limit, 20)),
            "sort": "+price",
            "in_stock": "true",
        }
        if ctx.min_price:
            params["price_from"] = ctx.min_price
        if ctx.max_price:
            params["price_to"] = ctx.max_price

        try:
            resp = httpx.get(ENDPOINT, params=params, timeout=ctx.timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise AdapterError(f"Yahoo!ショッピングAPIへの接続に失敗しました: {exc}") from exc
        except ValueError as exc:
            raise AdapterError(f"Yahoo!ショッピングAPIの応答を解析できませんでした: {exc}") from exc

        offers: list[Offer] = []
        for hit in (data or {}).get("hits", [])[: ctx.limit]:
            offer = self._to_offer(hit)
            if offer is not None:
                offers.append(offer)
        return offers

    # ------------------------------------------------------------------
    def _to_offer(self, hit: dict[str, Any]) -> Offer | None:
        price = hit.get("price")
        name = hit.get("name")
        if not price or not name:
            return None

        shipping = self._shipping_of(hit)
        points = self._points_of(hit, int(price))

        seller = hit.get("seller") or {}
        condition = "used" if str(hit.get("condition", "new")).lower() == "used" else "new"

        return Offer(
            platform=self.key,
            platform_label=self.label,
            title=str(name),
            price=int(price),
            url=str(hit.get("url") or ""),
            shop=str(seller.get("name") or ""),
            shipping=shipping,
            points=points,
            condition=condition,  # type: ignore[arg-type]
            in_stock=bool(hit.get("inStock", True)),
            source="api",
            note=shipping.note if shipping.kind != "free" else "",
            jan=str(hit.get("janCode")) if hit.get("janCode") else None,
        )

    @staticmethod
    def _shipping_of(hit: dict[str, Any]) -> ShippingPolicy:
        shipping = hit.get("shipping") or {}
        name = str(shipping.get("name") or "")
        if "条件" in name:
            return ShippingPolicy.conditional(
                ASSUMED_SHIPPING_FEE, ASSUMED_FREE_LINE, note=f"{name}(無料ラインは推定)"
            )
        if "無料" in name:
            return ShippingPolicy.free(name)
        if name:
            return ShippingPolicy.unknown(ASSUMED_SHIPPING_FEE, note=f"{name}(推定)")
        return ShippingPolicy.unknown(ASSUMED_SHIPPING_FEE)

    @staticmethod
    def _points_of(hit: dict[str, Any], price: int) -> list[PointReward]:
        point = hit.get("point") or {}
        amount = point.get("amount")
        if isinstance(amount, (int, float)) and amount > 0:
            times = point.get("times") or 1
            return [
                PointReward(
                    label=f"PayPayポイント(基本{times}倍)",
                    fixed_amount=int(amount),
                    limited=False,
                )
            ]
        return [PointReward(label="PayPayポイント(基本1%)", rate=0.01)]
