"""辞書(JSON)から ``Offer`` を組み立てる共通ヘルパ。

手動入力アダプタとデモデータの両方で使う。JSONの形式:

.. code-block:: json

    {
      "title": "商品名",
      "price": 19800,
      "shop": "○○ストア",
      "url": "https://...",
      "shipping": {"kind": "conditional_free", "fee": 660, "free_threshold": 3980},
      "points": [{"label": "基本ポイント", "rate": 0.01}],
      "coupon": 500,
      "fees": [{"label": "代引き手数料", "amount": 330}],
      "condition": "new",
      "delivery_days": 2
    }
"""

from __future__ import annotations

from typing import Any

from ..models import Fee, Offer, PointReward, ShippingPolicy


def shipping_from_dict(data: Any) -> ShippingPolicy:
    if data is None:
        return ShippingPolicy.unknown()
    if isinstance(data, (int, float)):
        return ShippingPolicy.flat(int(data)) if data else ShippingPolicy.free()
    if isinstance(data, str):
        return ShippingPolicy.free() if "無料" in data else ShippingPolicy.unknown()
    if not isinstance(data, dict):
        return ShippingPolicy.unknown()

    kind = str(data.get("kind") or "").strip()
    fee = int(data.get("fee") or 0)
    threshold = data.get("free_threshold")
    note = str(data.get("note") or "")
    remote = int(data.get("remote_surcharge") or 0)

    if kind == "free" or (not kind and fee == 0 and threshold is None):
        return ShippingPolicy(kind="free", fee=0, remote_surcharge=remote, note=note or "送料無料")
    if kind == "conditional_free" or (not kind and threshold is not None):
        return ShippingPolicy(
            kind="conditional_free",
            fee=fee,
            free_threshold=int(threshold) if threshold is not None else None,
            remote_surcharge=remote,
            note=note or (f"{int(threshold):,}円以上で無料" if threshold is not None else ""),
        )
    if kind == "unknown":
        return ShippingPolicy(kind="unknown", fee=fee, remote_surcharge=remote, note=note or "送料は要確認")
    return ShippingPolicy(kind="flat", fee=fee, remote_surcharge=remote, note=note or f"一律{fee:,}円")


def point_from_dict(data: dict[str, Any]) -> PointReward:
    return PointReward(
        label=str(data.get("label") or "ポイント還元"),
        rate=float(data.get("rate") or 0.0),
        fixed_amount=int(data["fixed_amount"]) if data.get("fixed_amount") is not None else None,
        cap=int(data["cap"]) if data.get("cap") is not None else None,
        basis=data.get("basis") or "item",
        limited=bool(data.get("limited", False)),
        note=str(data.get("note") or ""),
    )


def offer_from_dict(
    data: dict[str, Any],
    *,
    platform: str,
    label: str,
    source: str = "manual",
) -> Offer:
    return Offer(
        platform=platform,
        platform_label=label,
        title=str(data.get("title") or ""),
        price=int(data.get("price") or 0),
        url=str(data.get("url") or ""),
        shop=str(data.get("shop") or ""),
        shipping=shipping_from_dict(data.get("shipping")),
        points=[point_from_dict(p) for p in (data.get("points") or []) if isinstance(p, dict)],
        coupon=int(data.get("coupon") or 0),
        fees=[
            Fee(label=str(f.get("label") or "手数料"), amount=int(f.get("amount") or 0))
            for f in (data.get("fees") or [])
            if isinstance(f, dict)
        ],
        condition=data.get("condition") or "new",
        in_stock=bool(data.get("in_stock", True)),
        delivery_days=int(data["delivery_days"]) if data.get("delivery_days") is not None else None,
        source=source,
        note=str(data.get("note") or ""),
        jan=str(data["jan"]) if data.get("jan") else None,
        model_number=str(data["model_number"]) if data.get("model_number") else None,
    )


def matches(query: str, offer: Offer) -> bool:
    """検索語の各トークンが商品名に含まれるか(簡易マッチ)。"""
    tokens = [t for t in query.replace("　", " ").split() if t]
    if not tokens:
        return True
    haystack = f"{offer.title} {offer.shop}".lower()
    return all(t.lower() in haystack for t in tokens)
