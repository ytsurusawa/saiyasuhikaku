"""コマンドライン版「最安比較」。

使い方:
    python -m saiyasu "ワイヤレスイヤホン" --spu 5 --lyp --gonotsuku
"""

from __future__ import annotations

import argparse
import json
import sys

from .comparator import Comparator
from .models import ComparisonResult, RankedOffer
from .platforms import PLATFORM_LABELS
from .profile import PointProfile
from .textutil import display_width, pad, truncate, yen

HEADERS = ["順位", "プラットフォーム", "商品価格", "送料", "手数料", "ポイント", "実質価格", "1位との差"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saiyasu",
        description="Amazon・楽天・Yahoo!ショッピング・価格.comなどを送料込み・ポイント還元込みで一括比較します。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="例: python -m saiyasu \"Anker 充電器\" --spu 5 --lyp --gonotsuku --prime",
    )
    parser.add_argument("query", nargs="?", help="商品名(検索語)")
    parser.add_argument(
        "--platforms",
        help=f"比較対象を絞る(カンマ区切り)。指定可能: {','.join(PLATFORM_LABELS)}",
    )
    parser.add_argument("--per-platform", type=int, default=1, help="1プラットフォームあたりの表示件数(既定1)")
    parser.add_argument("--limit", type=int, default=5, help="各APIから取得する件数(既定5)")
    parser.add_argument("--timeout", type=float, default=8.0, help="APIタイムアウト秒(既定8)")

    points = parser.add_argument_group("ポイント還元の条件")
    points.add_argument("--spu", type=float, default=0.0, help="楽天SPUの上乗せ%%(例: 5 で+5%%)")
    points.add_argument("--kaimawari", type=int, default=0, help="楽天買い回りの購入店舗数")
    points.add_argument("--lyp", action="store_true", help="LYPプレミアム会員(+2%%)")
    points.add_argument("--gonotsuku", action="store_true", help="5のつく日などのキャンペーン(+4%%)")
    points.add_argument("--paypay-step", type=float, default=0.0, help="PayPayステップの上乗せ%%")
    points.add_argument("--prime", action="store_true", help="Amazonプライム会員(配送料無料)")
    points.add_argument("--amazon-card", type=float, default=0.0, help="Amazonカードの還元率%%")
    points.add_argument(
        "--point-value", type=float, default=1.0, help="通常ポイント1ptの円換算価値(既定1.0)"
    )
    points.add_argument(
        "--limited-point-value",
        type=float,
        default=0.9,
        help="期間限定ポイント1ptの円換算価値(既定0.9)",
    )

    other = parser.add_argument_group("その他")
    other.add_argument("--remote", action="store_true", help="沖縄・離島など追加送料がかかる地域")
    other.add_argument("--used", action="store_true", help="中古(メルカリなど)も比較対象に含める")
    other.add_argument("--no-demo", action="store_true", help="サンプルデータへのフォールバックを無効化")
    other.add_argument("--json", action="store_true", help="結果をJSONで出力")
    return parser


def profile_from_args(args: argparse.Namespace) -> PointProfile:
    return PointProfile(
        point_value=args.point_value,
        limited_point_value=args.limited_point_value,
        rakuten_spu_rate=args.spu / 100.0,
        rakuten_kaimawari_shops=args.kaimawari,
        lyp_premium=args.lyp,
        yahoo_day_campaign=args.gonotsuku,
        paypay_step_rate=args.paypay_step / 100.0,
        amazon_prime=args.prime,
        amazon_card_rate=args.amazon_card / 100.0,
        remote_area=args.remote,
        include_used=args.used,
    )


# ----------------------------------------------------------------------
def _row_cells(row: RankedOffer) -> list[str]:
    b = row.breakdown
    mark = "★" if row.is_best else " "
    shipping = "無料" if b.shipping_fee == 0 else yen(b.shipping_fee)
    if row.offer.shipping.needs_check:
        shipping += "?"
    points = f"-{b.point_value_yen:,}円" if b.point_value_yen else "-"
    diff = "—" if row.is_best else f"+{row.diff_from_best:,}円"
    label = row.offer.platform_label + ("(中古)" if row.offer.condition != "new" else "")
    return [
        f"{mark}{row.rank}",
        truncate(label, 22),
        yen(b.item_price),
        shipping,
        yen(b.fee_total) if b.fee_total else "-",
        points,
        yen(b.effective_price),
        diff,
    ]


def render_table(result: ComparisonResult) -> str:
    rows = [_row_cells(r) for r in result.ranked]
    if not rows:
        return "(比較できる出品がありません)"

    widths = [
        max(display_width(HEADERS[i]), *(display_width(r[i]) for r in rows))
        for i in range(len(HEADERS))
    ]
    aligns = ["left", "left", "right", "right", "right", "right", "right", "right"]

    def line(char: str = "─") -> str:
        return "┼".join(char * (w + 2) for w in widths)

    out = [
        "│".join(f" {pad(HEADERS[i], widths[i], align='center')} " for i in range(len(HEADERS))),
        line(),
    ]
    for cells in rows:
        out.append(
            "│".join(f" {pad(cells[i], widths[i], align=aligns[i])} " for i in range(len(cells)))
        )
    return "\n".join(out)


def render_details(result: ComparisonResult, top: int = 3) -> str:
    lines: list[str] = []
    for row in result.ranked[:top]:
        b = row.breakdown
        offer = row.offer
        lines.append(f"\n【{row.rank}位】{offer.platform_label}  {truncate(offer.title, 50)}")
        if offer.shop:
            lines.append(f"  ショップ: {offer.shop}")
        lines.append(f"  商品価格: {yen(b.item_price)}")
        lines.append(f"  送料    : {offer.shipping.describe(offer.price)}")
        if b.coupon:
            lines.append(f"  クーポン: -{yen(b.coupon)}")
        for fee in offer.fees:
            lines.append(f"  {fee.label}: {yen(fee.amount)}")
        lines.append(f"  支払総額: {yen(b.cash_total)}")
        for point in b.point_lines:
            tag = "(期間限定)" if point.limited else ""
            lines.append(f"  ＋{point.label}{tag}: {point.amount:,}pt → {yen(point.value_yen)}相当")
        lines.append(
            f"  実質価格: {yen(b.effective_price)}  (実質還元率 {b.effective_point_rate * 100:.1f}%)"
        )
        if offer.delivery_days is not None:
            lines.append(f"  お届け目安: 約{offer.delivery_days}日")
        if offer.url:
            lines.append(f"  URL: {offer.url}")
        if offer.note:
            lines.append(f"  備考: {offer.note}")
    return "\n".join(lines)


def render(result: ComparisonResult) -> str:
    out = [
        "",
        f"■ 検索語: {result.query}",
        "",
        render_table(result),
        "",
        "─" * 60,
        f"◎ 結論: {result.verdict()}",
    ]
    if len(result.ranked) >= 2:
        out.append(f"   最安と最高の差は {yen(result.savings_vs_worst())} です。")
    out.append("─" * 60)
    out.append(render_details(result))

    out.append("\n■ 取得状況")
    for status in result.statuses:
        source = {"api": "実データ", "manual": "手動入力", "demo": "サンプル"}.get(status.source, status.source)
        detail = f" - {status.message}" if status.message else ""
        out.append(f"  [{source}] {status.label}: {status.offer_count}件{detail}")

    if result.warnings:
        out.append("\n■ ご注意")
        for warning in result.warnings:
            out.append(f"  ※ {warning}")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.query:
        parser.print_help()
        return 1

    comparator = Comparator(allow_demo=not args.no_demo)
    result = comparator.compare(
        args.query,
        profile=profile_from_args(args),
        platforms=[p.strip() for p in args.platforms.split(",")] if args.platforms else None,
        per_platform=args.per_platform,
        limit_per_search=args.limit,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render(result))
    return 0 if result.ranked else 2


if __name__ == "__main__":
    sys.exit(main())
