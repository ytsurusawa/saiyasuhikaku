"""`.env` の読み込み。

外部依存を増やさないため、必要最小限の .env パーサを内蔵する
(`KEY=VALUE` / `export KEY=VALUE` / `#` コメント / クォート除去)。
すでに環境変数が設定されている場合はそちらを優先する
(シェルで渡した値を .env が上書きしないため)。
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = ".env"


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    # 行末のインラインコメントを落とす(クォートされていない場合のみ)
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def parse_env(text: str) -> dict[str, str]:
    """`.env` の中身を辞書にする。"""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            out[key] = _unquote(value)
    return out


def load_dotenv(path: str | os.PathLike[str] = DEFAULT_ENV_FILE, *, override: bool = False) -> dict[str, str]:
    """`.env` を読み込んで環境変数に反映し、実際に設定した値を返す。

    ファイルが無い場合は何もしない(APIキー未設定でもデモで動くため)。
    """
    env_path = Path(path)
    if not env_path.is_file():
        return {}
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    applied: dict[str, str] = {}
    for key, value in parse_env(text).items():
        if not override and os.environ.get(key):
            continue
        if value == "":
            continue  # 空欄は「未設定」として扱う
        os.environ[key] = value
        applied[key] = value
    return applied
