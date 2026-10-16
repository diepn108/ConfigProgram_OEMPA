from pathlib import Path

import numpy as np

from tests.test_pa_callback_integrity_2600us import main as run_callback_integrity


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_single_rx7_stage1.txt"
COMPRESSION_PATH = PROJECT_DIR / "data" / "pa_0deg_2600us_ascan.npy"
RX7_OUTPUT_PATH = PROJECT_DIR / "data" / "pa_0deg_2600us_rx7_ascan.npy"


def summarize(samples):
    nonzero_indices = np.flatnonzero(samples)
    first = int(nonzero_indices[0]) if nonzero_indices.size else None
    last = int(nonzero_indices[-1]) if nonzero_indices.size else None
    suffix_start = last + 1 if last is not None else 0
    return {
        "first_nonzero": first,
        "last_nonzero": last,
        "nonzero_count": int(nonzero_indices.size),
        "zero_count": int(np.count_nonzero(samples == 0)),
        "zero_fraction": float(np.mean(samples == 0)),
        "zero_suffix_start": suffix_start,
        "zero_suffix": bool(np.all(samples[suffix_start:] == 0)),
    }


def print_late_windows(label, samples):
    print(f"{label} late-window activity")
    print("---------------------------")
    windows = (
        ("2-5 us", 200, 500),
        ("5-10 us", 500, 1000),
        ("10-20 us", 1000, 2000),
        ("20-30 us", 2000, 3001),
    )
    for name, start, stop in windows:
        window = samples[start:min(stop, samples.size)]
        rms = float(np.sqrt(np.mean(window.astype(np.float64) ** 2))) if window.size else 0.0
        print(
            f"{name}: RMS={rms:.4f}, nonzero="
            f"{int(np.count_nonzero(window))}/{window.size}, "
            f"zeros={int(np.count_nonzero(window == 0))}"
        )


def compare_with_compression():
    compression = np.load(COMPRESSION_PATH, allow_pickle=False)
    rx7 = np.load(RX7_OUTPUT_PATH, allow_pickle=False)

    print("\nOffline RX7 vs 16-RX Compression comparison")
    print("-------------------------------------------")
    print(
        f"Compression: shape={compression.shape}, dtype={compression.dtype}, "
        f"min/max={int(compression.min())}/{int(compression.max())}"
    )
    print(
        f"RX7: shape={rx7.shape}, dtype={rx7.dtype}, "
        f"min/max={int(rx7.min())}/{int(rx7.max())}"
    )

    if compression.shape != rx7.shape or compression.dtype != rx7.dtype:
        raise RuntimeError("RX7 and Compression waveforms differ in shape or dtype.")

    compression_summary = summarize(compression)
    rx7_summary = summarize(rx7)
    for label, summary in (("Compression", compression_summary), ("RX7", rx7_summary)):
        print(
            f"{label}: first/last nonzero={summary['first_nonzero']}/"
            f"{summary['last_nonzero']}; nonzero={summary['nonzero_count']}; "
            f"zeros={summary['zero_count']}/{compression.size} "
            f"({summary['zero_fraction']:.6%}); "
            f"zero_suffix_start={summary['zero_suffix_start']}; "
            f"suffix_all_zero={summary['zero_suffix']}"
        )

    compression_mask = compression != 0
    rx7_mask = rx7 != 0
    intersection = int(np.count_nonzero(compression_mask & rx7_mask))
    union = int(np.count_nonzero(compression_mask | rx7_mask))
    jaccard = intersection / union if union else 1.0
    print(
        f"Nonzero-mask overlap: intersection={intersection}, union={union}, "
        f"differing_positions={int(np.count_nonzero(compression_mask != rx7_mask))}, "
        f"Jaccard={jaccard:.6f}"
    )

    common = compression_mask & rx7_mask
    if np.count_nonzero(common):
        compression_common = compression[common].astype(np.float64)
        rx7_common = rx7[common].astype(np.float64)
        compression_rms = float(np.sqrt(np.mean(compression_common ** 2)))
        rx7_rms = float(np.sqrt(np.mean(rx7_common ** 2)))
        if (
            compression_common.size > 1
            and np.std(compression_common) > 0
            and np.std(rx7_common) > 0
        ):
            correlation = float(np.corrcoef(compression_common, rx7_common)[0, 1])
            correlation_text = f"{correlation:.6f}"
        else:
            correlation_text = "undefined (constant/one-sample overlap)"
        print(
            f"Common-support amplitudes: count={compression_common.size}, "
            f"Compression RMS={compression_rms:.4f}, RX7 RMS={rx7_rms:.4f}, "
            f"Pearson r={correlation_text}"
        )
    else:
        print("Common-support amplitudes: no overlapping nonzero samples")

    print_late_windows("Compression", compression)
    print_late_windows("RX7", rx7)
    print("[INFO] Waveform peaks are not interpreted as physical echoes.")


def main():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)
    if not COMPRESSION_PATH.exists():
        raise FileNotFoundError(COMPRESSION_PATH)
    if RX7_OUTPUT_PATH.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {RX7_OUTPUT_PATH}")

    result = run_callback_integrity(
        config_path=CONFIG_PATH,
        output_path=RX7_OUTPUT_PATH,
        expected_compression_type=0,
        expected_point_count=3001,
        expected_point_factor=256,
        expected_rx_elements=[7],
    )

    if result != 0:
        print("[STOP] RX7 callback acquisition or metadata verification failed.")
        return result

    compare_with_compression()
    print("[STOP] RX7 Stage 2 complete; no further hardware experiment will be run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())