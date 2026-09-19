"""端末表示用のユーティリティ(全角文字を考慮した桁揃え)。"""

from __future__ import annotations

import unicodedata


def display_width(text: str) -> int:
    """全角(東アジア文字)を2桁として数えた表示幅。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1
    return width


def pad(text: str, width: int, *, align: str = "left") -> str:
    """表示幅ベースで空白を詰める。"""
    space = max(0, width - display_width(text))
    if align == "right":
        return " " * space + text
    if align == "center":
        left = space // 2
        return " " * left + text + " " * (space - left)
    return text + " " * space


def truncate(text: str, width: int) -> str:
    """表示幅 ``width`` に収まるよう末尾を切り詰める。"""
    if display_width(text) <= width:
        return text
    out = ""
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


def yen(value: int) -> str:
    return f"{value:,}円"
