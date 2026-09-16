"""Single entrypoint for the live pipeline: predicts every crop, builds the
crop comparison, and writes both to Supabase. This is what the Modal cron
job calls -- also runnable locally for testing without Modal/Supabase set up
(pass write=False to skip the Supabase step).
"""
from datetime import date

from config import CROPS, crop_checkpoints
from predict_live import predict, completed_periods, pick_checkpoint, \
    fetch_current_weather_and_moisture, fetch_current_stress, latest_available_cdl_year
from build_dataset import NEEDS_STRESS
from compare_crops import build_comparison


def run(as_of: date = None, write: bool = True):
    as_of = as_of or date.today()

    # Each crop can be on a different checkpoint now (wheat's spring
    # calendar vs. corn/soybean's summer one), so both the weather/moisture
    # fetch and what gets written to Supabase per crop need to be computed
    # per crop, not off one shared checkpoint.
    checkpoint_names = {}
    needed_periods = set()
    stress_periods = set()
    for crop in CROPS:
        done = completed_periods(as_of, crop)
        checkpoint_name = pick_checkpoint(done, crop)
        checkpoint_names[crop] = checkpoint_name
        if checkpoint_name:
            needed_periods.update(crop_checkpoints(crop)[checkpoint_name])
            if (crop, checkpoint_name) in NEEDS_STRESS:
                stress_periods.update(crop_checkpoints(crop)[checkpoint_name])

    if not needed_periods:
        print(f"As of {as_of}, not enough of the season has elapsed for any checkpoint model.")
        return

    weather_moisture_cache = fetch_current_weather_and_moisture(as_of.year, sorted(needed_periods))
    # Only fetched at all when some active checkpoint this run actually
    # needs it (see build_dataset.NEEDS_STRESS) -- most checkpoints don't.
    stress_cache = fetch_current_stress(as_of.year, sorted(stress_periods)) if stress_periods else None
    cdl_year = latest_available_cdl_year()

    predictions = {}
    for crop in CROPS:
        if checkpoint_names[crop] is None:
            print(f"[{crop}] As of {as_of}, not enough of the season has elapsed -- skipping.")
            continue
        predictions[crop] = predict(crop, as_of, weather_moisture_cache, cdl_year, stress_cache)

    comparison = build_comparison(as_of, predictions=predictions)
    # always save locally first, so a Supabase failure below doesn't lose the
    # computed result -- predict() already saves its own CSVs per crop
    comparison_path = f"data/processed/crop_comparison_{as_of.isoformat()}.csv"
    comparison.to_csv(comparison_path, index=False)
    print(f"Saved comparison to {comparison_path}")

    if write:
        from supabase_writer import write_live_predictions, write_crop_comparison
        for crop, df in predictions.items():
            write_live_predictions(df, as_of.isoformat(), checkpoint_names[crop])
        write_crop_comparison(comparison, as_of.isoformat())
    else:
        print("write=False, skipping Supabase")

    return predictions, comparison


if __name__ == "__main__":
    import sys
    write = "--no-write" not in sys.argv
    run(write=write)
