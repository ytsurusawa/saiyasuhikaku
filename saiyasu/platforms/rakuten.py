"""楽天市場アダプタ(楽天ウェブサービス 楽天市場商品検索API)。

必要な環境変数:
  RAKUTEN_APP_ID        楽天アプリID(必須)
  RAKUTEN_AFFILIATE_ID  アフィリエイトID(任意)
"""

from __future__ import annotations

from typing import Any

import httpx

from ..models import Offer, PointReward, ShippingPolicy
from .base import AdapterError, PlatformAdapter, SearchContext

ENDPOINT = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

# 楽天の「共通の送料込みライン」。送料別の出品はこの金額を境に無料になる店が多い。
RAKUTEN_FREE_SHIPPING_LINE = 3980
# 送料別かつ無料ライン未満の場合に置く推定送料。
ASSUMED_SHIPPING_FEE = 660


class RakutenAdapter(PlatformAdapter):
    key = "rakuten"
    label = "楽天市場"
    required_env = ("RAKUTEN_APP_ID",)

    def search(self, ctx: SearchContext) -> list[Offer]:
        params: dict[str, Any] = {
            "applicationId": self.env("RAKUTEN_APP_ID"),
            "keyword": ctx.query,
            "hits": max(1, min(ctx.limit, 30)),
            "sort": "+itemPrice",
            "availability": 1,
            "format": "json",
        }
        affiliate_id = self.env("RAKUTEN_AFFILIATE_ID")
        if affiliate_id:
            params["affiliateId"] = affiliate_id
        if ctx.min_price:
            params["minPrice"] = ctx.min_price
        if ctx.max_price:
            params["maxPrice"] = ctx.max_price

        try:
            resp = httpx.get(ENDPOINT, params=params, timeout=ctx.timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise AdapterError(f"楽天市場APIへの接続に失敗しました: {exc}") from exc
        except ValueError as exc:
            raise AdapterError(f"楽天市場APIの応答を解析できませんでした: {exc}") from exc

        if isinstance(data, dict) and data.get("error"):
            raise AdapterError(
                f"楽天市場API: {data.get('error')} {data.get('error_description', '')}".strip()
            )

        offers: list[Offer] = []
        for entry in (data or {}).get("Items", [])[: ctx.limit]:
            # APIバージョンによって {"Item": {...}} と {...} の両方がありうる
            item = entry.get("Item", entry) if isinstance(entry, dict) else {}
            offer = self._to_offer(item)
            if offer is not None:
                offers.append(offer)
        return offers

    # ------------------------------------------------------------------
    def _to_offer(self, item: dict[str, Any]) -> Offer | None:
        price = item.get("itemPrice")
        title = item.get("itemName")
        if not price or not title:
            return None

        # postageFlag: 0 = 送料込み/無料, 1 = 送料別
        if item.get("postageFlag") == 0:
            shipping = ShippingPolicy.free("送料込み")
        else:
            shipping = ShippingPolicy.conditional(
                ASSUMED_SHIPPING_FEE,
                RAKUTEN_FREE_SHIPPING_LINE,
                note=f"送料別。{RAKUTEN_FREE_SHIPPING_LINE:,}円以上で無料の店舗が多い(推定)",
            )

        # pointRate は倍率(1.0 = 1倍 = 1%)
        try:
            multiplier = float(item.get("pointRate") or 1.0)
        except (TypeError, ValueError):
            multiplier = 1.0
        points = [
            PointReward(
                label=f"楽天ポイント{multiplier:g}倍",
                rate=multiplier / 100.0,
                limited=multiplier > 1.0,
            )
        ]

        return Offer(
            platform=self.key,
            platform_label=self.label,
            title=str(title),
            price=int(price),
            url=str(item.get("affiliateUrl") or item.get("itemUrl") or ""),
            shop=str(item.get("shopName") or ""),
            shipping=shipping,
            points=points,
            in_stock=bool(item.get("availability", 1)),
            source="api",
            note=shipping.note if shipping.kind != "free" else "",
        )
