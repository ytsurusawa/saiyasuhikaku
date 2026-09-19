"""Amazon.co.jp アダプタ(Product Advertising API v5)。

PA-API v5 は AWS SigV4 署名が必要なため、署名処理を内製している
(外部SDKへの依存を避けるため)。

必要な環境変数:
  AMAZON_ACCESS_KEY  PA-APIのアクセスキー
  AMAZON_SECRET_KEY  PA-APIのシークレットキー
  AMAZON_PARTNER_TAG アソシエイトタグ(例: example-22)
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
from typing import Any

import httpx

from ..models import Offer, PointReward, ShippingPolicy
from .base import AdapterError, PlatformAdapter, SearchContext

HOST = "webservices.amazon.co.jp"
REGION = "us-west-2"  # 日本のマーケットプレイスもPA-API v5では us-west-2 を使う
SERVICE = "ProductAdvertisingAPI"
PATH = "/paapi5/searchitems"
TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"

RESOURCES = [
    "ItemInfo.Title",
    "Offers.Listings.Price",
    "Offers.Listings.Condition",
    "Offers.Listings.DeliveryInfo.IsFreeShippingEligible",
    "Offers.Listings.DeliveryInfo.IsPrimeEligible",
    "Offers.Listings.MerchantInfo",
]

# Amazonの「合計2,000円以上で通常配送無料」(プライム会員は無料)
AMAZON_FREE_SHIPPING_LINE = 2000
ASSUMED_SHIPPING_FEE = 460


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, datestamp: str) -> bytes:
    k_date = _sign(f"AWS4{secret}".encode("utf-8"), datestamp)
    k_region = _sign(k_date, REGION)
    k_service = _sign(k_region, SERVICE)
    return _sign(k_service, "aws4_request")


class AmazonAdapter(PlatformAdapter):
    key = "amazon"
    label = "Amazon.co.jp"
    required_env = ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG")

    def search(self, ctx: SearchContext) -> list[Offer]:
        payload: dict[str, Any] = {
            "Keywords": ctx.query,
            "SearchIndex": "All",
            "ItemCount": max(1, min(ctx.limit, 10)),
            "PartnerTag": self.env("AMAZON_PARTNER_TAG"),
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.co.jp",
            "Resources": RESOURCES,
        }
        if ctx.min_price:
            payload["MinPrice"] = ctx.min_price * 100
        if ctx.max_price:
            payload["MaxPrice"] = ctx.max_price * 100

        body = json.dumps(payload, ensure_ascii=False)
        headers = self._signed_headers(body)

        try:
            resp = httpx.post(
                f"https://{HOST}{PATH}",
                content=body.encode("utf-8"),
                headers=headers,
                timeout=ctx.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise AdapterError(
                f"Amazon PA-APIがエラーを返しました({exc.response.status_code})。"
                "キーとアソシエイトタグ、売上要件をご確認ください"
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterError(f"Amazon PA-APIへの接続に失敗しました: {exc}") from exc
        except ValueError as exc:
            raise AdapterError(f"Amazon PA-APIの応答を解析できませんでした: {exc}") from exc

        if isinstance(data, dict) and data.get("Errors"):
            first = data["Errors"][0]
            raise AdapterError(f"Amazon PA-API: {first.get('Message', first)}")

        items = ((data or {}).get("SearchResult") or {}).get("Items") or []
        offers: list[Offer] = []
        for item in items[: ctx.limit]:
            offer = self._to_offer(item, ctx)
            if offer is not None:
                offers.append(offer)
        return offers

    # ------------------------------------------------------------------
    def _signed_headers(self, body: str) -> dict[str, str]:
        access_key = self.env("AMAZON_ACCESS_KEY")
        secret_key = self.env("AMAZON_SECRET_KEY")
        now = _dt.datetime.now(_dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")

        canonical_headers = (
            f"content-encoding:amz-1.0\n"
            f"content-type:application/json; charset=utf-8\n"
            f"host:{HOST}\n"
            f"x-amz-date:{amz_date}\n"
            f"x-amz-target:{TARGET}\n"
        )
        signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_request = "\n".join(
            ["POST", PATH, "", canonical_headers, signed_headers, payload_hash]
        )

        credential_scope = f"{datestamp}/{REGION}/{SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            _signing_key(secret_key, datestamp),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        authorization = (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "content-encoding": "amz-1.0",
            "content-type": "application/json; charset=utf-8",
            "host": HOST,
            "x-amz-date": amz_date,
            "x-amz-target": TARGET,
            "Authorization": authorization,
        }

    def _to_offer(self, item: dict[str, Any], ctx: SearchContext) -> Offer | None:
        listings = ((item.get("Offers") or {}).get("Listings")) or []
        if not listings:
            return None
        listing = listings[0]
        amount = ((listing.get("Price") or {}).get("Amount"))
        if amount is None:
            return None
        price = int(round(float(amount)))

        title = (((item.get("ItemInfo") or {}).get("Title") or {}).get("DisplayValue")) or ""
        delivery = listing.get("DeliveryInfo") or {}
        prime = bool(delivery.get("IsPrimeEligible"))
        profile = ctx.profile

        if delivery.get("IsFreeShippingEligible") or (prime and profile and profile.amazon_prime):
            shipping = ShippingPolicy.free("配送料無料" + ("(プライム)" if prime else ""))
        else:
            shipping = ShippingPolicy.conditional(
                ASSUMED_SHIPPING_FEE,
                AMAZON_FREE_SHIPPING_LINE,
                note=f"{AMAZON_FREE_SHIPPING_LINE:,}円以上の注文で通常配送無料(推定)",
            )

        condition = "new"
        sub = str((listing.get("Condition") or {}).get("Value", "New")).lower()
        if sub == "used":
            condition = "used"
        elif sub in ("refurbished", "collectible"):
            condition = "refurbished"

        merchant = (listing.get("MerchantInfo") or {}).get("Name") or "Amazon.co.jp"

        return Offer(
            platform=self.key,
            platform_label=self.label,
            title=str(title),
            price=price,
            url=str(item.get("DetailPageURL") or ""),
            shop=str(merchant),
            shipping=shipping,
            # Amazonは商品により還元が無いことも多いため、既定は付けずプロフィールの
            # クレカ還元のみを載せる。ポイント対象商品はnoteで補足する。
            points=[PointReward(label="Amazonポイント(基本)", rate=0.01)] if prime else [],
            condition=condition,  # type: ignore[arg-type]
            source="api",
            note="プライム対象" if prime else "",
        )
