"""比較対象プラットフォームの一覧。"""

from __future__ import annotations

from .amazon import AmazonAdapter
from .base import PlatformAdapter
from .manual import ManualAdapter
from .rakuten import RakutenAdapter
from .yahoo import YahooAdapter

#: 比較対象。上から順に表示・取得する。
ADAPTERS: list[PlatformAdapter] = [
    AmazonAdapter(),
    RakutenAdapter(),
    YahooAdapter(),
    ManualAdapter("kakaku", "価格.com"),
    ManualAdapter("yodobashi", "ヨドバシ.com"),
    ManualAdapter("biccamera", "ビックカメラ.com"),
    ManualAdapter("aupay", "au PAY マーケット"),
    ManualAdapter("qoo10", "Qoo10"),
    ManualAdapter("mercari", "メルカリ"),
]

PLATFORM_LABELS: dict[str, str] = {a.key: a.label for a in ADAPTERS}


def all_adapters() -> list[PlatformAdapter]:
    return list(ADAPTERS)


def get_adapter(key: str) -> PlatformAdapter | None:
    for adapter in ADAPTERS:
        if adapter.key == key:
            return adapter
    return None
