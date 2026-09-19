"""CLIのテスト。"""

import json

import pytest

from saiyasu.cli import build_parser, main, profile_from_args, render
from saiyasu.comparator import Comparator
from saiyasu.textutil import display_width, pad, truncate


class TestTextUtil:
    def test_full_width_counts_as_two(self):
        assert display_width("楽天") == 4
        assert display_width("ab") == 2

    def test_pad_aligns_by_display_width(self):
        assert display_width(pad("楽天", 10)) == 10
        assert display_width(pad("Amazon", 10, align="right")) == 10

    def test_truncate_keeps_within_width(self):
        assert display_width(truncate("あ" * 20, 10)) <= 10
        assert truncate("短い", 10) == "短い"


class TestArgs:
    def test_percent_options_convert_to_rates(self):
        args = build_parser().parse_args(["商品", "--spu", "5", "--amazon-card", "2"])
        profile = profile_from_args(args)
        assert profile.rakuten_spu_rate == pytest.approx(0.05)
        assert profile.amazon_card_rate == pytest.approx(0.02)

    def test_flags(self):
        args = build_parser().parse_args(["商品", "--lyp", "--gonotsuku", "--used", "--remote"])
        profile = profile_from_args(args)
        assert profile.lyp_premium and profile.yahoo_day_campaign
        assert profile.include_used and profile.remote_area


class TestRender:
    def test_table_contains_every_platform_and_the_verdict(self):
        result = Comparator().compare("イヤホン")
        text = render(result)
        assert "最もお得なのは" in text
        assert "実質価格" in text
        for row in result.ranked:
            assert row.offer.platform_label in text

    def test_columns_stay_aligned_with_japanese_labels(self):
        text = render(Comparator().compare("加湿器"))
        table = [ln for ln in text.splitlines() if "│" in ln]
        widths = {display_width(ln) for ln in table}
        assert len(widths) == 1, f"列幅が揃っていません: {widths}"


class TestMain:
    def test_json_output_is_valid(self, capsys):
        assert main(["イヤホン", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["best"]["rank"] == 1

    def test_text_output(self, capsys):
        assert main(["イヤホン", "--spu", "5"]) == 0
        assert "◎ 結論" in capsys.readouterr().out

    def test_no_query_prints_help(self, capsys):
        assert main([]) == 1
        assert "usage" in capsys.readouterr().out.lower()

    def test_no_demo_without_keys_yields_nothing(self, capsys):
        assert main(["イヤホン", "--no-demo"]) == 2
