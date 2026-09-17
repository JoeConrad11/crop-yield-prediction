"""Layer 3 of the farmer-app agronomy roadmap (see ../ARCHITECTURE.md,
"Layer 3 -- Advice, sourced not invented"). Pairs a field's prediction with
why it came out that way, from two legitimate sources only -- never
model-generated prose:

  (a) the model's own SHAP explanation, reusing the exact feature row and
      model predict_field.py would use (see predict_field.build_field_prediction_row);
  (b) a cited Iowa State Extension finding, but only when the field's own
      computed growth stage AND its own measured stress metrics actually
      match the condition it describes (see advice_sources.py).

Deliberately separate from predict_field.py's return shape and reachable even
when the yield path refuses: growth stage (field_insights.field_growth_stage)
has no field-size limit, so a small field that correctly gets no yield number
can still get a sourced note if its stage/stress state warrants one -- same
principle as field_insights.py staying available where predict_field.py must
decline.
"""
from datetime import date

import numpy as np

from advice_sources import matching_notes
from explain_utils import shap_contributions
from field_insights import field_growth_stage
from predict_field import build_field_prediction_row


def field_advice(boundary: dict, crop: str, planting_date: str = None,
                  as_of: date = None, field_id: str = None) -> dict:
    as_of = as_of or date.today()

    stage = None
    if planting_date:
        stage_result = field_growth_stage(boundary, crop, planting_date, as_of)
        if "error" not in stage_result:
            stage = stage_result.get("stage")  # may legitimately be None (planted, not yet emerged)

    shap_explanation = None
    shap_unavailable_reason = None
    row = None

    built = build_field_prediction_row(boundary, crop, as_of, field_id=field_id)
    if "error" in built:
        # Same honest-refusal reasons predict_field() surfaces (small-field
        # coverage limits, season not started, etc.) -- not a failure of
        # this endpoint, just nothing to explain yet.
        shap_unavailable_reason = built["message"]
    else:
        row = built["row"]
        top, other_sum, other_count, base_value = shap_contributions(
            built["df"].iloc[0], built["features"], built["model"], top_n=5
        )
        shap_explanation = {
            "base_value_bu_acre": base_value,
            # trend_predict() returns a length-1 array for the "engineered"
            # variant (per-row, see feature_engineering.py) but a bare 0.0
            # for "baseline" -- np.ravel handles both without an isinstance
            # check, same trick explain_utils.py uses for expected_value.
            "trend_contribution_bu_acre": float(np.ravel(built["trend_pred"])[0]),
            "top_contributions": top,
            "other_contribution_bu_acre": other_sum,
            "other_feature_count": other_count,
        }

    sourced_notes = matching_notes(crop, stage["code"], row) if stage else []

    return {
        "crop": crop,
        "stage": stage,
        "shap_explanation": shap_explanation,
        "shap_unavailable_reason": shap_unavailable_reason,
        "sourced_notes": sourced_notes,
    }


if __name__ == "__main__":
    import sys

    demo_boundary = {
        "type": "Polygon",
        "coordinates": [[
            [-93.62, 41.99], [-93.61, 41.99], [-93.61, 41.98], [-93.62, 41.98], [-93.62, 41.99],
        ]],
    }
    crop = sys.argv[1] if len(sys.argv) > 1 else "corn"
    planting = sys.argv[2] if len(sys.argv) > 2 else "2026-05-12"
    result = field_advice(demo_boundary, crop, planting)
    for key, value in result.items():
        print(f"  {key}: {value}")
