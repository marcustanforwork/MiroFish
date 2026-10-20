import pytest

from app.services.oasis_profile_generator import OasisProfileGenerator
from app.utils.locale import set_locale


def _prompts():
    generator = object.__new__(OasisProfileGenerator)
    args = dict(entity_name="Ana", entity_type="EventHost", entity_summary="", entity_attributes={}, context="")
    return (
        generator._build_individual_persona_prompt(**args),
        generator._build_group_persona_prompt(**args),
    )


@pytest.fixture(autouse=True)
def restore_locale():
    yield
    set_locale("zh")


def test_english_runs_ask_for_english_country_names():
    set_locale("en")

    for prompt in _prompts():
        assert '"Singapore"' in prompt
        assert "使用中文" not in prompt


def test_chinese_runs_keep_chinese_country_names():
    set_locale("zh")

    for prompt in _prompts():
        assert '使用中文，如"中国"' in prompt
