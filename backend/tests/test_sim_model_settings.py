import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from sim_model_settings import sim_model_config  # noqa: E402


def test_nothing_set_gives_no_config():
    assert sim_model_config({}) is None


def test_reasoning_effort_alone():
    assert sim_model_config({"LLM_SIM_REASONING_EFFORT": "none"}) == {"reasoning_effort": "none"}


def test_cache_control_goes_in_the_request_body():
    config = sim_model_config({"LLM_SIM_REASONING_EFFORT": "none", "LLM_SIM_CACHE_CONTROL": "ephemeral"})

    assert config == {"reasoning_effort": "none", "extra_body": {"cache_control": {"type": "ephemeral"}}}


def test_cache_control_with_a_one_hour_lifetime():
    config = sim_model_config({"LLM_SIM_CACHE_CONTROL": "ephemeral:1h"})

    assert config == {"extra_body": {"cache_control": {"type": "ephemeral", "ttl": "1h"}}}


@pytest.mark.parametrize("value", ["", "  ", "off", "none"])
def test_cache_control_off_values(value):
    assert sim_model_config({"LLM_SIM_CACHE_CONTROL": value}) is None


def test_never_sets_max_tokens():
    config = sim_model_config({"LLM_SIM_REASONING_EFFORT": "low", "LLM_SIM_CACHE_CONTROL": "ephemeral"})

    assert "max_tokens" not in config
