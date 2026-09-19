""".env 読み込みのテスト。"""

import os

from saiyasu.config import load_dotenv, parse_env


class TestParseEnv:
    def test_basic_pairs(self):
        assert parse_env("A=1\nB=2") == {"A": "1", "B": "2"}

    def test_comments_and_blank_lines_are_ignored(self):
        assert parse_env("# comment\n\nA=1\n  # indented\n") == {"A": "1"}

    def test_export_prefix(self):
        assert parse_env("export RAKUTEN_APP_ID=abc") == {"RAKUTEN_APP_ID": "abc"}

    def test_quotes_are_stripped(self):
        assert parse_env('A="quoted"\nB=\'single\'') == {"A": "quoted", "B": "single"}

    def test_inline_comment_is_dropped(self):
        assert parse_env("A=value  # メモ") == {"A": "value"}

    def test_hash_inside_quotes_is_kept(self):
        assert parse_env('A="pass#word"') == {"A": "pass#word"}

    def test_value_may_contain_equals(self):
        assert parse_env("A=x=y") == {"A": "x=y"}

    def test_lines_without_equals_are_skipped(self):
        assert parse_env("garbage\nA=1") == {"A": "1"}


class TestLoadDotenv:
    def test_missing_file_is_a_noop(self, tmp_path):
        assert load_dotenv(tmp_path / "nope.env") == {}

    def test_values_are_applied_to_environ(self, tmp_path, monkeypatch):
        path = tmp_path / ".env"
        path.write_text("RAKUTEN_APP_ID=from-file\n", encoding="utf-8")
        monkeypatch.delenv("RAKUTEN_APP_ID", raising=False)

        assert load_dotenv(path) == {"RAKUTEN_APP_ID": "from-file"}
        assert os.environ["RAKUTEN_APP_ID"] == "from-file"

    def test_existing_environment_wins(self, tmp_path, monkeypatch):
        """シェルで渡した値を .env が上書きしないこと。"""
        path = tmp_path / ".env"
        path.write_text("RAKUTEN_APP_ID=from-file\n", encoding="utf-8")
        monkeypatch.setenv("RAKUTEN_APP_ID", "from-shell")

        assert load_dotenv(path) == {}
        assert os.environ["RAKUTEN_APP_ID"] == "from-shell"

    def test_override_is_opt_in(self, tmp_path, monkeypatch):
        path = tmp_path / ".env"
        path.write_text("RAKUTEN_APP_ID=from-file\n", encoding="utf-8")
        monkeypatch.setenv("RAKUTEN_APP_ID", "from-shell")

        load_dotenv(path, override=True)
        assert os.environ["RAKUTEN_APP_ID"] == "from-file"

    def test_blank_values_are_treated_as_unset(self, tmp_path, monkeypatch):
        """.env.example をそのままコピーしても「設定済み」にならないこと。"""
        path = tmp_path / ".env"
        path.write_text("RAKUTEN_APP_ID=\n", encoding="utf-8")
        monkeypatch.delenv("RAKUTEN_APP_ID", raising=False)

        assert load_dotenv(path) == {}
        assert "RAKUTEN_APP_ID" not in os.environ
