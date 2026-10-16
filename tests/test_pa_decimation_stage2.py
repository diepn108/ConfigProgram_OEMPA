from pathlib import Path

import numpy as np

from tests.test_pa_callback_integrity_2600us import main as run_callback_integrity


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_decimation_stage1.txt"
COMPRESSION_PATH = PROJECT_DIR / "data" / "pa_0deg_2600us_ascan.npy"
DECIMATION_PATH = PROJECT_DIR / "data" / "pa_0deg_2600us_decimation_ascan.npy"


def waveform_summary(samples):
    nonzero = np.flatnonzero(samples)
    first = int(nonzero[0]) if nonzero.size else None
    last = int(nonzero[-1]) if nonzero.size else None
    suffix_start = last + 1 if last is not None else 0
    return {
        "first_nonzero": first,
        "last_nonzero": last,
        "nonzero_count": int(nonzero.size),
        "zero_count": int(np.count_nonzero(samples == 0)),
        "zero_fraction": float(np.mean(samples == 0)),
        "suffix_start": suffix_start,
        "zero_suffix": bool(np.all(samples[suffix_start:] == 0)),
    }


def print_window_activity(label, samples, start, stop):
    window = samples[start:min(stop, samples.size)]
    rms = float(np.sqrt(np.mean(window.astype(np.float64) ** 2))) if window.size else 0.0
    print(
        f"{label}: RMS={rms:.4f}, nonzero="
        f"{int(np.count_nonzero(window))}/{window.size}, "
        f"zeros={int(np.count_nonzero(window == 0))}"
    )


def compare_saved_waveforms():
    if not COMPRESSION_PATH.exists():
        raise FileNotFoundError(COMPRESSION_PATH)
    if not DECIMATION_PATH.exists():
        raise FileNotFoundError(DECIMATION_PATH)

    compression = np.load(COMPRESSION_PATH, allow_pickle=False)
    decimation = np.load(DECIMATION_PATH, allow_pickle=False)

    print("\nOffline Compression vs Decimation comparison")
    print("---------------------------------------------")
    print(
        f"Compression: shape={compression.shape}, dtype={compression.dtype}, "
        f"min/max={int(compression.min())}/{int(compression.max())}"
    )
    print(
        f"Decimation: shape={decimation.shape}, dtype={decimation.dtype}, "
        f"min/max={int(decimation.min())}/{int(decimation.max())}"
    )

    if compression.shape != decimation.shape or compression.dtype != decimation.dtype:
        raise RuntimeError("Compression/Decimation arrays differ in shape or dtype.")

    compression_summary = waveform_summary(compression)
    decimation_summary = waveform_summary(decimation)
    for mode, summary in (
        ("Compression", compression_summary),
        ("Decimation", decimation_summary),
    ):
        print(
            f"{mode} support: first/last={summary['first_nonzero']}/"
            f"{summary['last_nonzero']}; nonzero={summary['nonzero_count']}; "
            f"zeros={summary['zero_count']}/{compression.size} "
            f"({summary['zero_fraction']:.6%}); "
            f"zero_suffix_start={summary['suffix_start']}; "
            f"suffix_all_zero={summary['zero_suffix']}"
        )

    compression_mask = compression != 0
    decimation_mask = decimation != 0
    intersection = int(np.count_nonzero(compression_mask & decimation_mask))
    union = int(np.count_nonzero(compression_mask | decimation_mask))
    differing = int(np.count_nonzero(compression_mask != decimation_mask))
    jaccard = intersection / union if union else 1.0
    print(
        f"Nonzero-mask overlap: intersection={intersection}, union={union}, "
        f"differing_positions={differing}, Jaccard={jaccard:.6f}"
    )

    common = compression_mask & decimation_mask
    if np.count_nonzero(common):
        old_common = compression[common].astype(np.float64)
        new_common = decimation[common].astype(np.float64)
        old_rms = float(np.sqrt(np.mean(old_common ** 2)))
        new_rms = float(np.sqrt(np.mean(new_common ** 2)))
        if old_common.size > 1 and np.std(old_common) > 0 and np.std(new_common) > 0:
            correlation = float(np.corrcoef(old_common, new_common)[0, 1])
            correlation_text = f"{correlation:.6f}"
        else:
            correlation_text = "undefined (constant/one-sample overlap)"
        print(
            f"Common-support amplitudes: count={old_common.size}, "
            f"Compression RMS={old_rms:.4f}, Decimation RMS={new_rms:.4f}, "
            f"Pearson r={correlation_text}"
        )
    else:
        print("Common-support amplitudes: no overlapping nonzero samples")

    print("Late-window activity (sample counts; 100 MHz):")
    windows = (
        ("2-5 us", 200, 500),
        ("5-10 us", 500, 1000),
        ("10-20 us", 1000, 2000),
        ("20-30 us", 2000, 3001),
    )
    for label, start, stop in windows:
        print(f"  Compression {label}: ", end="")
        print_window_activity("", compression, start, stop)
        print(f"  Decimation {label}: ", end="")
        print_window_activity("", decimation, start, stop)

    print("[INFO] Do not interpret early peaks or sparse late samples as specimen echoes.")


def main():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)
    if not COMPRESSION_PATH.exists():
        raise FileNotFoundError(COMPRESSION_PATH)
    if DECIMATION_PATH.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {DECIMATION_PATH}")

    result = run_callback_integrity(
        config_path=CONFIG_PATH,
        output_path=DECIMATION_PATH,
        expected_compression_type=1,
        expected_point_count=3001,
        expected_point_factor=1,
    )

    if result != 0:
        print("[STOP] Stage 2 acquisition/metadata validation did not pass.")
        return result

    compare_saved_waveforms()
    print("[STOP] Stage 2 complete; no further hardware test will be run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())