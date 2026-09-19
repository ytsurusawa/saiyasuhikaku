"""Web APIのテスト。"""

import pytest
from fastapi.testclient import TestClient

from saiyasu.api import app

client = TestClient(app)


def test_healthz():
    assert client.get("/healthz").json()["status"] == "ok"


def test_index_is_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "最安比較" in resp.text


def test_platforms_listing():
    data = client.get("/api/platforms").json()["platforms"]
    keys = {p["key"] for p in data}
    assert {"amazon", "rakuten", "yahoo", "kakaku"} <= keys
    amazon = next(p for p in data if p["key"] == "amazon")
    assert "AMAZON_ACCESS_KEY" in amazon["required_env"]


def test_compare_returns_a_ranked_list():
    resp = client.post("/api/compare", json={"query": "ワイヤレスイヤホン"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert data["best"]["rank"] == 1
    assert data["best"]["is_best"] is True
    prices = [r["breakdown"]["effective_price"] for r in data["results"]]
    assert prices == sorted(prices)
    assert data["verdict"]


def test_compare_breakdown_is_self_consistent():
    data = client.post("/api/compare", json={"query": "炊飯器"}).json()
    for row in data["results"]:
        b = row["breakdown"]
        assert b["cash_total"] == b["item_price"] + b["shipping_fee"] + b["fee_total"] - b["coupon"]
        assert b["effective_price"] == b["cash_total"] - b["point_value_yen"]


def test_profile_changes_the_ranking_inputs():
    body = {"query": "掃除機", "platforms": ["rakuten"]}
    plain = client.post("/api/compare", json=body).json()
    boosted = client.post(
        "/api/compare",
        json={**body, "profile": {"rakuten_spu_rate": 0.10, "limited_point_value": 1.0}},
    ).json()
    assert (
        boosted["results"][0]["breakdown"]["point_value_yen"]
        > plain["results"][0]["breakdown"]["point_value_yen"]
    )
    assert (
        boosted["results"][0]["breakdown"]["effective_price"]
        < plain["results"][0]["breakdown"]["effective_price"]
    )


def test_platform_filter_is_applied():
    data = client.post("/api/compare", json={"query": "鍋", "platforms": ["amazon"]}).json()
    assert {r["platform"] for r in data["results"]} == {"amazon"}


def test_used_items_are_opt_in():
    body = {"query": "ゲーム機", "platforms": ["mercari"]}
    assert client.post("/api/compare", json=body).json()["count"] == 0
    opted = client.post("/api/compare", json={**body, "profile": {"include_used": True}}).json()
    assert opted["count"] == 1


def test_blank_query_is_rejected():
    assert client.post("/api/compare", json={"query": "   "}).status_code == 400
    assert client.post("/api/compare", json={"query": ""}).status_code == 422


def test_out_of_range_profile_is_rejected():
    resp = client.post(
        "/api/compare", json={"query": "本", "profile": {"rakuten_spu_rate": 5.0}}
    )
    assert resp.status_code == 422
