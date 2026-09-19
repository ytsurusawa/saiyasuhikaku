"""一括比較のオーケストレーション。

全プラットフォームを並列に検索し、送料・ポイントを織り込んだ実質価格で
並べ替えて「どこで買うのが一番お得か」を返す。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from .matching import DEFAULT_THRESHOLD, MatchReport, filter_offers
from .models import ComparisonResult, Offer, PlatformStatus, RankedOffer
from .platforms import AdapterError, PlatformAdapter, SearchContext, all_adapters
from .platforms.demo import demo_offers
from .pricing import build_breakdown
from .profile import PointProfile

DEFAULT_PER_PLATFORM = 1


class Comparator:
    """プラットフォーム横断の価格比較。"""

    def __init__(
        self,
        adapters: Iterable[PlatformAdapter] | None = None,
        *,
        allow_demo: bool = True,
        max_workers: int = 8,
    ) -> None:
        self.adapters = list(adapters) if adapters is not None else all_adapters()
        self.allow_demo = allow_demo
        self.max_workers = max_workers

    # ------------------------------------------------------------------
    def compare(
        self,
        query: str,
        *,
        profile: PointProfile | None = None,
        platforms: Iterable[str] | None = None,
        per_platform: int = DEFAULT_PER_PLATFORM,
        limit_per_search: int = 5,
        timeout: float = 8.0,
        min_price: int | None = None,
        max_price: int | None = None,
        strict_matching: bool = True,
        match_threshold: float = DEFAULT_THRESHOLD,
    ) -> ComparisonResult:
        query = (query or "").strip()
        profile = profile or PointProfile()
        if not query:
            return ComparisonResult(
                query=query,
                ranked=[],
                statuses=[],
                profile_summary=profile.summary(),
                warnings=["商品名を入力してください。"],
                match_report=MatchReport(),
            )

        wanted = set(platforms) if platforms else None
        targets = [a for a in self.adapters if wanted is None or a.key in wanted]
        ctx = SearchContext(
            query=query,
            limit=max(1, limit_per_search),
            profile=profile,
            timeout=timeout,
            min_price=min_price,
            max_price=max_price,
        )

        collected: list[tuple[PlatformStatus, list[Offer]]] = []
        if targets:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(targets))) as pool:
                collected = list(pool.map(lambda a: self._fetch(a, ctx), targets))

        statuses = [status for status, _ in collected]
        offers: list[Offer] = [o for _, chunk in collected for o in chunk]

        warnings: list[str] = []
        if any(s.source == "demo" for s in statuses):
            warnings.append(
                "一部またはすべての価格はサンプル(デモ)データです。"
                "実データで比較するには各プラットフォームのAPIキーを設定してください。"
            )

        # 別商品を比べてしまわないよう、検索意図と一致しない出品を落とす
        report = filter_offers(
            query, offers, threshold=match_threshold, strict=strict_matching
        )
        warnings.extend(report.warnings())

        ranked = self.rank(report.kept, profile=profile, per_platform=per_platform)
        if not ranked:
            if report.excluded:
                warnings.append(
                    "検索語に一致する出品が残りませんでした。"
                    "型番まで含めた正確な商品名で検索するか、検索語を短くしてお試しください。"
                )
            else:
                warnings.append("条件に合う出品が見つかりませんでした。検索語を短くしてお試しください。")

        return ComparisonResult(
            query=query,
            ranked=ranked,
            statuses=statuses,
            profile_summary=profile.summary(),
            warnings=warnings,
            match_report=report,
        )

    # ------------------------------------------------------------------
    def rank(
        self,
        offers: Iterable[Offer],
        *,
        profile: PointProfile | None = None,
        per_platform: int = DEFAULT_PER_PLATFORM,
    ) -> list[RankedOffer]:
        """実質価格の安い順に並べる。"""
        profile = profile or PointProfile()

        rows: list[tuple[Offer, "object"]] = []
        for offer in offers:
            if offer.price <= 0 or not offer.in_stock:
                continue
            if offer.condition != "new" and not profile.include_used:
                continue
            rows.append((offer, build_breakdown(offer, profile)))

        # 実質価格 → 支払総額 → お届け日数 の順で比較
        rows.sort(
            key=lambda row: (
                row[1].effective_price,  # type: ignore[attr-defined]
                row[1].cash_total,  # type: ignore[attr-defined]
                row[0].delivery_days if row[0].delivery_days is not None else 99,
            )
        )

        if per_platform > 0:
            seen: dict[str, int] = {}
            kept = []
            for offer, breakdown in rows:
                count = seen.get(offer.platform, 0)
                if count >= per_platform:
                    continue
                seen[offer.platform] = count + 1
                kept.append((offer, breakdown))
            rows = kept

        ranked: list[RankedOffer] = []
        best_price = rows[0][1].effective_price if rows else 0  # type: ignore[attr-defined]
        for index, (offer, breakdown) in enumerate(rows, start=1):
            ranked.append(
                RankedOffer(
                    rank=index,
                    offer=offer,
                    breakdown=breakdown,  # type: ignore[arg-type]
                    diff_from_best=breakdown.effective_price - best_price,  # type: ignore[attr-defined]
                )
            )
        return ranked

    # ------------------------------------------------------------------
    def _fetch(self, adapter: PlatformAdapter, ctx: SearchContext) -> tuple[PlatformStatus, list[Offer]]:
        ok, reason = adapter.available()
        if ok:
            try:
                offers = adapter.search(ctx)
            except AdapterError as exc:
                return self._demo_fallback(adapter, ctx, str(exc))
            except Exception as exc:  # アダプタの不具合で比較全体を止めない
                return self._demo_fallback(adapter, ctx, f"予期しないエラー: {exc}")

            if offers:
                source = offers[0].source
                return (
                    PlatformStatus(
                        platform=adapter.key,
                        label=adapter.label,
                        ok=True,
                        offer_count=len(offers),
                        source=source,
                        message=reason,
                    ),
                    offers,
                )
            return self._demo_fallback(adapter, ctx, "該当する商品が見つかりませんでした")

        return self._demo_fallback(adapter, ctx, reason)

    def _demo_fallback(
        self, adapter: PlatformAdapter, ctx: SearchContext, reason: str
    ) -> tuple[PlatformStatus, list[Offer]]:
        if not self.allow_demo:
            return (
                PlatformStatus(
                    platform=adapter.key,
                    label=adapter.label,
                    ok=False,
                    source="none",
                    message=f"{reason}（--no-demo のため取得なし）" if reason else "取得なし",
                ),
                [],
            )
        offers = demo_offers(ctx.query, adapter.key, adapter.label, limit=ctx.limit)
        return (
            PlatformStatus(
                platform=adapter.key,
                label=adapter.label,
                ok=bool(offers),
                offer_count=len(offers),
                source="demo",
                message=f"{reason}（サンプルデータで代替）" if reason else "サンプルデータ",
            ),
            offers,
        )


def compare(query: str, **kwargs) -> ComparisonResult:
    """モジュールレベルのショートカット。"""
    return Comparator().compare(query, **kwargs)
