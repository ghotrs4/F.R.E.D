import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def load_series(json_path: Path):
    with json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    telemetries = payload.get("telemetries", {})
    analog = telemetries.get("ADC_analog_value", {})
    millivolts = telemetries.get("ADC_millivolts_value", {})

    analog_data = analog.get("data", [[], []])
    mv_data = millivolts.get("data", [[], []])

    analog_times = analog_data[0] if len(analog_data) > 0 else []
    analog_values = analog_data[1] if len(analog_data) > 1 else []
    mv_times = mv_data[0] if len(mv_data) > 0 else []
    mv_values = mv_data[1] if len(mv_data) > 1 else []

    if not analog_times or not analog_values or not mv_times or not mv_values:
        raise ValueError("Missing ADC_analog_value or ADC_millivolts_value series in JSON data.")

    analog_length = min(len(analog_times), len(analog_values))
    mv_length = min(len(mv_times), len(mv_values))

    analog_times = analog_times[:analog_length]
    analog_values = analog_values[:analog_length]
    mv_times = mv_times[:mv_length]
    mv_values = mv_values[:mv_length]

    t0 = min(analog_times[0], mv_times[0])
    analog_times = [t - t0 for t in analog_times]
    mv_times = [t - t0 for t in mv_times]

    return analog_times, analog_values, mv_times, mv_values


def main():
    script_dir = Path(__file__).resolve().parent
    default_input = script_dir.parent / "data" / "teleplot_2026-2-13_8-45.json"
    default_output = script_dir / "adc_analog_vs_millivolts.png"

    parser = argparse.ArgumentParser(
        description="Plot ADC_raw_bytes_value vs ADC_calibrated_millivolts_value from JSON export."
    )
    parser.add_argument("--input", type=Path, default=default_input, help="Path to Teleplot JSON file")
    parser.add_argument("--output", type=Path, default=default_output, help="Path to output PNG")
    parser.add_argument("--show", action="store_true", help="Show the plot window")
    args = parser.parse_args()

    analog_times, adc_analog, mv_times, adc_mv = load_series(args.input)

    plt.figure(figsize=(9, 6))
    plt.plot(analog_times, adc_analog, linewidth=1.4, label="ADC_raw_bytes_value")
    plt.plot(mv_times, adc_mv, linewidth=1.4, label="ADC_calibrated_millivolts_value")
    plt.title("ADC Analog and Millivolts vs Time")
    plt.xlabel("Time (s)")
    plt.ylabel("Millivolts / ADC Value")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.output, dpi=150)
    print(f"Saved plot to: {args.output}")

    if args.show:
        plt.show()
    else:
        plt.close()


if __name__ == "__main__":
    main()