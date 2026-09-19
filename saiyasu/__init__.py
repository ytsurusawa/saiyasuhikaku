"""最安比較 — 日本の主要通販を「送料込み・ポイント還元込み」で一括比較する。"""

from .comparator import Comparator, compare
from .models import ComparisonResult, Offer, PointReward, ShippingPolicy
from .pricing import build_breakdown, effective_price
from .profile import PointProfile

__version__ = "0.1.0"

__all__ = [
    "Comparator",
    "compare",
    "ComparisonResult",
    "Offer",
    "PointReward",
    "ShippingPolicy",
    "PointProfile",
    "build_breakdown",
    "effective_price",
]
