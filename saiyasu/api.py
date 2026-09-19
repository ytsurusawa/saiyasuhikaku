"""Web API + 画面配信(FastAPI)。

起動:
    uvicorn saiyasu.api:app --reload
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .comparator import Comparator
from .config import load_dotenv
from .platforms import ADAPTERS
from .profile import PointProfile

load_dotenv()  # uvicorn 起動時に .env を読み込む

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="最安比較 API",
    description="Amazon・楽天市場・Yahoo!ショッピング・価格.comなどを送料込み・ポイント還元込みで一括比較します。",
    version=__version__,
)


class ProfileIn(BaseModel):
    """ポイント還元条件。率は「%」ではなく小数(0.05 = 5%)。"""

    point_value: float = Field(1.0, ge=0, le=2)
    limited_point_value: float = Field(0.9, ge=0, le=2)
    rakuten_spu_rate: float = Field(0.0, ge=0, le=1)
    rakuten_kaimawari_shops: int = Field(0, ge=0, le=20)
    lyp_premium: bool = False
    yahoo_day_campaign: bool = False
    paypay_step_rate: float = Field(0.0, ge=0, le=1)
    amazon_prime: bool = False
    amazon_card_rate: float = Field(0.0, ge=0, le=1)
    remote_area: bool = False
    include_used: bool = False

    def to_profile(self) -> PointProfile:
        return PointProfile(**self.model_dump())


class CompareIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="商品名")
    profile: ProfileIn = Field(default_factory=ProfileIn)
    platforms: list[str] | None = None
    per_platform: int = Field(1, ge=1, le=5)
    limit_per_search: int = Field(5, ge=1, le=20)
    allow_demo: bool = True
    strict_matching: bool = Field(True, description="検索語と一致しない出品を除外するか")
    match_threshold: float = Field(0.6, ge=0.0, le=1.0, description="商品名の一致しきい値")


@app.get("/api/platforms")
def platforms() -> dict[str, Any]:
    """比較対象プラットフォームと、その取得手段の状態を返す。"""
    out = []
    for adapter in ADAPTERS:
        ok, reason = adapter.available()
        out.append(
            {
                "key": adapter.key,
                "label": adapter.label,
                "has_public_api": adapter.has_public_api,
                "ready": ok,
                "reason": reason,
                "required_env": list(adapter.required_env),
            }
        )
    return {"platforms": out}


@app.post("/api/compare")
def compare(payload: CompareIn) -> dict[str, Any]:
    """一括比較して、実質価格の安い順に返す。"""
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="商品名を入力してください。")

    comparator = Comparator(allow_demo=payload.allow_demo)
    result = comparator.compare(
        query,
        profile=payload.profile.to_profile(),
        platforms=payload.platforms,
        per_platform=payload.per_platform,
        limit_per_search=payload.limit_per_search,
        strict_matching=payload.strict_matching,
        match_threshold=payload.match_threshold,
    )
    return result.to_dict()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
