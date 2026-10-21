import pytest

from app.config import Config, max_retries_from
from app.utils.llm_client import LLMClient


def test_unset_keeps_the_sdk_default():
    assert max_retries_from({}) == 2


def test_a_number_is_used():
    assert max_retries_from({"LLM_MAX_RETRIES": " 8 "}) == 8


@pytest.mark.parametrize("value", ["-1", "lots", ""])
def test_anything_else_falls_back_to_the_default(value):
    assert max_retries_from({"LLM_MAX_RETRIES": value}) == 2


def test_the_client_retries_as_configured(monkeypatch):
    monkeypatch.setattr(Config, "LLM_MAX_RETRIES", 8)

    client = LLMClient(api_key="test-key", base_url="http://localhost:9", model="m")

    assert client.client.max_retries == 8
