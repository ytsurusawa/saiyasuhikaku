"""プラットフォーム別アダプタ。"""

from .base import AdapterError, PlatformAdapter, SearchContext
from .registry import ADAPTERS, PLATFORM_LABELS, all_adapters, get_adapter

__all__ = [
    "AdapterError",
    "PlatformAdapter",
    "SearchContext",
    "ADAPTERS",
    "PLATFORM_LABELS",
    "all_adapters",
    "get_adapter",
]
