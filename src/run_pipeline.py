"""Single entrypoint for the live pipeline: predicts every crop, builds the
crop comparison, and writes both to Supabase. This is what the Modal cron
job calls -- also runnable locally for testing without Modal/Supabase set up
(pass write=False to skip the Supabase step).
"""
from datetime import date

from config import CROPS
from predict_live import predict, completed_periods, pick_checkpoint, \
    fetch_current_weather_and_moisture, latest_available_cdl_year, CHECKPOINTS
from compare_crops import build_comparison


def run(as_of: date = None, write: bool = True):
    as_of = as_of or date.today()
    done = completed_periods(as_of)
    checkpoint_name = pick_checkpoint(done)

    if checkpoint_name is None:
        print(f"As of {as_of}, not enough of the season has elapsed for any checkpoint model.")
        return

    periods = CHECKPOINTS[checkpoint_name]
    weather_moisture_cache = fetch_current_weather_and_moisture(as_of.year, periods)
    cdl_year = latest_available_cdl_year()

    predictions = {}
    for crop in CROPS:
        predictions[crop] = predict(crop, as_of, weather_moisture_cache, cdl_year)

    comparison = build_comparison(as_of, predictions=predictions)
    # always save locally first, so a Supabase failure below doesn't lose the
    # computed result -- predict() already saves its own CSVs per crop
    comparison_path = f"data/processed/crop_comparison_{as_of.isoformat()}.csv"
    comparison.to_csv(comparison_path, index=False)
    print(f"Saved comparison to {comparison_path}")

    if write:
        from supabase_writer import write_live_predictions, write_crop_comparison
        for crop, df in predictions.items():
            write_live_predictions(df, as_of.isoformat(), checkpoint_name)
        write_crop_comparison(comparison, as_of.isoformat())
    else:
        print("write=False, skipping Supabase")

    return predictions, comparison


if __name__ == "__main__":
    import sys
    write = "--no-write" not in sys.argv
    run(write=write)
