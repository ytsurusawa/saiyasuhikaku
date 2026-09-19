"""公開検索APIが無いサイト向けの手動入力アダプタ。

価格.com・メルカリ・ヨドバシ.com などは誰でも使える商品検索APIが公開されて
いないため、価格を手で(あるいは自前の取得処理で)JSONに入れて比較に混ぜる。

JSONの場所は環境変数 ``SAIYASU_MANUAL_OFFERS`` (既定: ``data/manual_offers.json``)。
形式は ``{"kakaku": [ <オファー>, ... ], "mercari": [ ... ]}``。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..models import Offer
from .base import AdapterError, PlatformAdapter, SearchContext
from .spec import matches, offer_from_dict

DEFAULT_PATH = "data/manual_offers.json"


def _load_all() -> dict[str, Any]:
    path = Path(os.environ.get("SAIYASU_MANUAL_OFFERS", DEFAULT_PATH))
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise AdapterError(f"手動入力ファイルを読み込めませんでした({path}): {exc}") from exc
    return data if isinstance(data, dict) else {}


class ManualAdapter(PlatformAdapter):
    """公開APIが無いサイト用。JSONに書かれた価格を読み込む。"""

    has_public_api = False

    def __init__(self, key: str, label: str, note: str = "") -> None:
        self.key = key
        self.label = label
        self.note = note

    def available(self) -> tuple[bool, str]:
        entries = _load_all().get(self.key) or []
        if entries:
            return True, f"手動入力データ {len(entries)}件を使用"
        return False, f"{self.label}は公開検索APIが無いため、手動入力データが無ければデモ値で表示します"

    def search(self, ctx: SearchContext) -> list[Offer]:
        entries = _load_all().get(self.key) or []
        offers = [
            offer_from_dict(e, platform=self.key, label=self.label, source="manual")
            for e in entries
            if isinstance(e, dict)
        ]
        hits = [o for o in offers if matches(ctx.query, o) and o.price > 0]
        hits.sort(key=lambda o: o.price)
        return hits[: ctx.limit]
