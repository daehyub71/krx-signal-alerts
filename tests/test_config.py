"""config — .env 로더가 CI 환경변수를 덮어쓰지 않는지."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from alerts import config


def write_env(tmp_path: Path, body: str) -> Path:
    """임시 .env 파일을 만든다."""
    p = tmp_path / ".env"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_env_sets_missing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KSA_TEST_A", raising=False)
    config.load_env(write_env(tmp_path, "KSA_TEST_A=hello\n"))
    assert os.environ["KSA_TEST_A"] == "hello"


def test_load_env_does_not_overwrite_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI가 주입한 Secret을 로컬 .env가 덮어쓰면 원인을 찾기 어려운 사고가 난다."""
    monkeypatch.setenv("KSA_TEST_B", "from-ci")
    config.load_env(write_env(tmp_path, "KSA_TEST_B=from-dotenv\n"))
    assert os.environ["KSA_TEST_B"] == "from-ci"


def test_load_env_skips_comments_and_blanks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KSA_TEST_C", raising=False)
    config.load_env(write_env(tmp_path, "# 주석\n\n  \nKSA_TEST_C = \"quoted\" \n"))
    assert os.environ["KSA_TEST_C"] == "quoted"


def test_load_env_missing_file_is_not_an_error(tmp_path: Path) -> None:
    config.load_env(tmp_path / "nope.env")


def test_require_raises_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KSA_TEST_D", raising=False)
    with pytest.raises(RuntimeError, match="KSA_TEST_D"):
        config.require("KSA_TEST_D")


def test_require_raises_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """빈 문자열을 값으로 인정하면 나중에 인증 오류로 뒤늦게 터진다."""
    monkeypatch.setenv("KSA_TEST_E", "   ")
    with pytest.raises(RuntimeError):
        config.require("KSA_TEST_E")
