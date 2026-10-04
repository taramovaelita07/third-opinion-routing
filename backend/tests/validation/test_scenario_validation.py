"""Verify the jury-facing synthetic scenario validation stays reproducible."""

from scripts.validate_scenarios import validate_scenarios


def test_all_selected_clinical_style_scenarios_pass() -> None:
    results = validate_scenarios()

    assert len(results) == 4
    assert all(result.passed for result in results)
    assert {result.case_id for result in results} == {
        "ct-lung-nodule",
        "mmg-birads-4",
        "ct-pneumothorax",
        "conclusion-conflict",
    }
