"""プラットフォームアダプタの共通インタフェース。

各モールごとに ``PlatformAdapter`` を実装し、検索語から ``Offer`` のリストを返す。
APIキーが無い場合は ``available()`` が ``False`` を返し、比較側がデモデータに
フォールバックする。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..models import Offer
from ..profile import PointProfile

DEFAULT_TIMEOUT = 8.0


@dataclass
class SearchContext:
    """検索1回分の条件。"""

    query: str
    limit: int = 3
    profile: PointProfile | None = None
    timeout: float = DEFAULT_TIMEOUT
    min_price: int | None = None
    max_price: int | None = None


class AdapterError(RuntimeError):
    """アダプタが取得に失敗したことを表す。比較処理は続行する。"""


class PlatformAdapter(ABC):
    """1プラットフォーム分の検索アダプタ。"""

    key: str = ""
    label: str = ""
    #: 公式の検索APIがあるか(無い場合は手動入力/CSV取り込みで補う)
    has_public_api: bool = True
    #: APIを使うために必要な環境変数
    required_env: tuple[str, ...] = ()

    def available(self) -> tuple[bool, str]:
        """APIを実行できる状態か。``(可否, 理由)`` を返す。"""
        if not self.has_public_api:
            return False, f"{self.label}は公開検索APIが無いため、手動入力/CSV取り込みで比較します"
        missing = [name for name in self.required_env if not os.environ.get(name)]
        if missing:
            return False, f"{'、'.join(missing)} が未設定のためデモデータを使用します"
        return True, ""

    @abstractmethod
    def search(self, ctx: SearchContext) -> list[Offer]:
        """検索語に一致する出品を返す。失敗時は ``AdapterError`` を送出する。"""

    # -- 小道具 ---------------------------------------------------------
    @staticmethod
    def env(name: str, default: str = "") -> str:
        return os.environ.get(name, default)
