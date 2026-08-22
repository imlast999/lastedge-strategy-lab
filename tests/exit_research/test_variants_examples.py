"""
Example tests for exit_research variants.

Task 12.1 — All 10 variants registered in VARIANT_BY_NAME
"""


def test_all_variants_registered():
    """
    All 12 exit-strategy variants must be present in VARIANT_BY_NAME.

    Validates: Requirements 2.1
    """
    from core.exit_research.variants import VARIANT_BY_NAME

    expected_slugs = {
        "rr_1_2",
        "rr_1_25",
        "rr_1_3",
        "rr_1_35",
        "rr_1_4",
        "trailing_atr",
        "trailing_ema",
        "dynamic_atr",
        "break_even",
        "partial_close",
        "trailing_donchian",
        "time_exit",
    }

    assert len(VARIANT_BY_NAME) == 12, (
        f"Expected 12 variants, got {len(VARIANT_BY_NAME)}. "
        f"Found: {set(VARIANT_BY_NAME.keys())}"
    )
    assert set(VARIANT_BY_NAME.keys()) == expected_slugs, (
        f"Slug mismatch.\n"
        f"  Missing : {expected_slugs - set(VARIANT_BY_NAME.keys())}\n"
        f"  Extra   : {set(VARIANT_BY_NAME.keys()) - expected_slugs}"
    )
