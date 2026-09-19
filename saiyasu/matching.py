"""商品同定（別商品を比較してしまわないための絞り込み）。

キーワード検索の結果をそのまま並べると、あるモールでは本体が、別のモールでは
互換ケースやアクセサリがヒットし、「別の商品同士」を比較してしまう。
ここでは次の4つの手掛かりで、検索意図と一致しない出品を落とす。

1. 型番   … 検索語に型番が含まれるなら、商品名にも同じ型番が必要
2. JAN    … JANが取れた出品同士は、代表JANと一致するものだけを残す
3. 商品名 … 検索語のトークンが商品名にどれだけ含まれるか（一致スコア）
4. 付属品 … 「ケース」「フィルム」など、検索語に無いアクセサリ語を含む出品を落とす

加えて、残った出品の価格が中央値から大きく外れる場合は「要確認」の印を付ける
（除外はしない。本当に掘り出し物の可能性があるため）。
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field

from .models import Offer

#: 商品名に含まれていたら「本体ではない」と判断する語
ACCESSORY_WORDS: tuple[str, ...] = (
    "ケース", "カバー", "フィルム", "保護シート", "スキンシール", "ステッカー",
    "スタンド", "ホルダー", "マウント", "ポーチ", "収納", "バッグ",
    "交換用", "互換品", "互換バッテリー", "modelのみ", "空箱", "説明書のみ",
    "ストラップ", "グリップ", "クリーナー", "変換アダプタ", "変換ケーブル",
)

#: 型番らしき文字列（英字と数字が混ざった3文字以上のトークン）
MODEL_RE = re.compile(r"[A-Za-z]+[-_]?[0-9]+[A-Za-z0-9\-_]*|[0-9]+[-_]?[A-Za-z]+[A-Za-z0-9\-_]*")

#: 一致スコアの既定しきい値（検索語トークンの6割が商品名に含まれていること）
DEFAULT_THRESHOLD = 0.6

#: 価格が中央値のこの倍率を下回る／上回ると「要確認」にする
CHEAP_OUTLIER_RATIO = 0.35
EXPENSIVE_OUTLIER_RATIO = 3.0
MIN_OFFERS_FOR_OUTLIER = 3


def normalize(text: str) -> str:
    """全角・半角、大文字・小文字、記号のゆれを吸収する。"""
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[\s　・/／,，.．\(\)（）\[\]【】]+", " ", text).strip()


def _squash(text: str) -> str:
    """比較用に区切り記号を落とした形（WH-1000XM5 → wh1000xm5）。"""
    return re.sub(r"[-_\s]+", "", normalize(text))


def extract_models(text: str) -> set[str]:
    """文字列から型番らしきトークンを取り出す。"""
    models = set()
    for token in MODEL_RE.findall(normalize(text)):
        squashed = _squash(token)
        if len(squashed) >= 3 and any(c.isdigit() for c in squashed) and any(c.isalpha() for c in squashed):
            models.add(squashed)
    return models


def tokenize(query: str) -> list[str]:
    """検索語をトークンに分ける。"""
    return [t for t in normalize(query).split(" ") if t]


def title_score(query: str, title: str) -> float:
    """検索語のトークンが商品名にどれだけ含まれるか（0.0〜1.0）。"""
    tokens = tokenize(query)
    if not tokens:
        return 1.0
    haystack = _squash(title)
    hits = sum(1 for token in tokens if _squash(token) in haystack)
    return hits / len(tokens)


def is_accessory(query: str, title: str) -> str | None:
    """商品名がアクセサリを指していれば、その語を返す。

    検索語自体にその語が入っている場合（「iPhone ケース」を探している等）は
    アクセサリ扱いしない。
    """
    normalized_query = normalize(query)
    normalized_title = normalize(title)
    for word in ACCESSORY_WORDS:
        target = normalize(word)
        if target in normalized_title and target not in normalized_query:
            return word
    return None


@dataclass
class Excluded:
    """除外した出品とその理由。"""

    offer: Offer
    reason: str  # "model" | "jan" | "title" | "accessory"
    detail: str

    @property
    def reason_label(self) -> str:
        return {
            "model": "型番が一致しない",
            "jan": "JANコードが異なる",
            "title": "商品名が検索語と一致しない",
            "accessory": "本体ではない（アクセサリ）",
        }.get(self.reason, self.reason)

    def to_dict(self) -> dict:
        data = self.offer.to_dict()
        data.update({"reason": self.reason, "reason_label": self.reason_label, "detail": self.detail})
        return data


@dataclass
class MatchReport:
    """絞り込みの結果。"""

    kept: list[Offer] = field(default_factory=list)
    excluded: list[Excluded] = field(default_factory=list)
    reference_jan: str | None = None
    suspect: list[Offer] = field(default_factory=list)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)

    def warnings(self) -> list[str]:
        out: list[str] = []
        if self.excluded:
            by_reason: dict[str, int] = {}
            for item in self.excluded:
                by_reason[item.reason_label] = by_reason.get(item.reason_label, 0) + 1
            detail = "、".join(f"{label} {count}件" for label, count in by_reason.items())
            out.append(f"検索語と一致しない{self.excluded_count}件を比較から除外しました（{detail}）。")
        for offer in self.suspect:
            out.append(
                f"{offer.platform_label}の「{offer.title[:30]}」は価格が相場から大きく外れています。"
                "同一商品か（付属品・保証・並行輸入品でないか）ご確認ください。"
            )
        return out

    def to_dict(self) -> dict:
        return {
            "kept_count": len(self.kept),
            "excluded_count": self.excluded_count,
            "reference_jan": self.reference_jan,
            "excluded": [e.to_dict() for e in self.excluded],
        }


def _pick_reference_jan(scored: list[tuple[Offer, float]]) -> str | None:
    """代表JANを決める。一致スコアが高いものを優先し、同点なら多数決。"""
    counts: dict[str, int] = {}
    best: dict[str, float] = {}
    for offer, score in scored:
        if not offer.jan:
            continue
        counts[offer.jan] = counts.get(offer.jan, 0) + 1
        best[offer.jan] = max(best.get(offer.jan, 0.0), score)
    if not counts:
        return None
    return max(counts, key=lambda jan: (best[jan], counts[jan]))


def filter_offers(
    query: str,
    offers: list[Offer],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    strict: bool = True,
) -> MatchReport:
    """検索意図と一致しない出品を落として ``MatchReport`` を返す。

    ``strict=False`` の場合は判定だけ行い、除外はしない（スコアは記録する）。
    """
    report = MatchReport()
    if not offers:
        return report

    query_models = extract_models(query)
    scored: list[tuple[Offer, float]] = []

    for offer in offers:
        offer.match_score = title_score(query, offer.title)
        scored.append((offer, offer.match_score))

    reference_jan = _pick_reference_jan(scored)
    report.reference_jan = reference_jan

    for offer, score in scored:
        reason: tuple[str, str] | None = None

        # 1. 型番（最も強い手掛かり）
        if query_models:
            title_models = extract_models(offer.title)
            if offer.model_number:
                title_models |= {_squash(offer.model_number)}
            if title_models and not (query_models & title_models):
                reason = ("model", f"検索語の型番 {'/'.join(sorted(query_models))} が商品名にありません")

        # 2. JAN（代表JANと違うものは別商品）
        if reason is None and reference_jan and offer.jan and offer.jan != reference_jan:
            reason = ("jan", f"JAN {offer.jan} は代表JAN {reference_jan} と異なります")

        # 3. アクセサリ
        if reason is None:
            word = is_accessory(query, offer.title)
            if word:
                reason = ("accessory", f"商品名に「{word}」が含まれます")

        # 4. 商品名の一致スコア
        if reason is None and score < threshold:
            reason = ("title", f"一致スコア {score:.0%}（しきい値 {threshold:.0%}）")

        if reason is not None and strict:
            report.excluded.append(Excluded(offer=offer, reason=reason[0], detail=reason[1]))
        else:
            report.kept.append(offer)

    _flag_price_outliers(report)
    return report


def _flag_price_outliers(report: MatchReport) -> None:
    """残った出品のうち、価格が相場から大きく外れるものに印を付ける。"""
    prices = [o.price for o in report.kept if o.price > 0]
    if len(prices) < MIN_OFFERS_FOR_OUTLIER:
        return
    median = statistics.median(prices)
    if median <= 0:
        return
    for offer in report.kept:
        if offer.price <= 0 or offer.condition != "new":
            continue  # 中古は安くて当然なので対象外
        if offer.price < median * CHEAP_OUTLIER_RATIO or offer.price > median * EXPENSIVE_OUTLIER_RATIO:
            offer.suspect_price = True
            report.suspect.append(offer)
