from app.services.oasis_profile_generator import OasisProfileGenerator
from app.utils.locale import set_locale


def test_rule_based_fallback_country_is_not_chinese_on_english_runs():
    set_locale("en")
    try:
        generator = object.__new__(OasisProfileGenerator)
        for entity_type in ("MediaOutlet", "Organization"):
            profile = generator._generate_profile_rule_based(
                entity_name="X", entity_type=entity_type, entity_summary="", entity_attributes={}
            )
            assert profile["country"] != "中国"
    finally:
        set_locale("zh")
