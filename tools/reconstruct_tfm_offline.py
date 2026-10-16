"""Explicitly parameterized offline TFM diagnostic; never imports the device API.

Legacy rate/start must be supplied by the caller. Output is experimental and
does not identify defects or establish physical probe mapping/material facts.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oempa.dataset import load_dataset
from oempa.tfm import ImageGrid, LinearGeometry, TimingAssumption, TFMRequest, display_image, reconstruct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--pitch-mm", type=float, required=True)
    parser.add_argument("--velocity-m-s", type=float, required=True)
    parser.add_argument("--legacy-rate-mhz", type=float)
    parser.add_argument("--legacy-start-us", type=float)
    parser.add_argument("--method", choices=("nearest", "linear"), default="nearest")
    parser.add_argument("--x-min-mm", type=float, default=-10)
    parser.add_argument("--x-max-mm", type=float, default=10)
    parser.add_argument("--z-min-mm", type=float, default=0)
    parser.add_argument("--z-max-mm", type=float, default=40)
    parser.add_argument("--x-pixels", type=int, default=201)
    parser.add_argument("--z-pixels", type=int, default=201)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.legacy_rate_mhz is None) != (args.legacy_start_us is None):
        parser.error("Supply both legacy rate and start, or neither for complete captured metadata.")
    digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    source = load_dataset(args.source)
    timing = None if args.legacy_rate_mhz is None else TimingAssumption(args.legacy_rate_mhz * 1e6, args.legacy_start_us * 1e-6)
    grid = ImageGrid(args.x_min_mm * 1e-3, args.x_max_mm * 1e-3, args.x_pixels, args.z_min_mm * 1e-3, args.z_max_mm * 1e-3, args.z_pixels)
    request = TFMRequest(LinearGeometry(source.data.shape[0], args.pitch_mm * 1e-3), args.velocity_m_s, grid, args.method, timing)
    started = time.perf_counter()
    result = reconstruct(source, request, source_label=str(args.source))
    elapsed = time.perf_counter() - started
    assert hashlib.sha256(args.source.read_bytes()).hexdigest() == digest
    args.output.mkdir(parents=True, exist_ok=True)
    np.savez(args.output / "tfm_raw.npz", image=result.image, x_m=result.x_m, z_m=result.z_m, element_x_m=result.element_x_m)
    report = {"source_file": str(args.source), "source_sha256": digest, "source_metadata": asdict(result.source_metadata),
              "request": asdict(result.request), "sampling_hz": result.sampling_hz, "start_s": result.start_s,
              "timing_origin": result.timing_origin, "mapping_verified": result.mapping_verified, "warnings": result.warnings,
              "image_shape": result.image.shape, "method": result.method, "configuration_revision": result.configuration_revision,
              "reconstructed_at_utc": result.reconstructed_at_utc, "elapsed_seconds": elapsed}
    (args.output / "provenance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    view = display_image(result, "db")
    figure = Figure(figsize=(8, 7), layout="tight")
    FigureCanvasAgg(figure)
    axes = figure.add_subplot(111)
    mesh = axes.pcolormesh(result.x_m * 1e3, result.z_m * 1e3, view.values, shading="auto", cmap=view.cmap, vmin=view.vmin, vmax=view.vmax)
    axes.set_xlim(result.x_m[0] * 1e3, result.x_m[-1] * 1e3)
    axes.set_ylim(result.z_m[-1] * 1e3, result.z_m[0] * 1e3)
    axes.set_aspect("equal", adjustable="box")
    axes.set_xlabel("Lateral position (mm)")
    axes.set_ylabel("Depth (mm)")
    axes.set_title("Experimental/unverified TFM — no defect interpretation\nProbe/channel mapping: Unverified")
    figure.colorbar(mesh, ax=axes).set_label(view.label)
    figure.supxlabel(f"Assumed pitch {args.pitch_mm:g} mm, velocity {args.velocity_m_s:g} m/s\n{result.sampling_hz / 1e6:g} MHz, start {result.start_s * 1e6:g} µs — {result.timing_origin}", fontsize=9)
    figure.savefig(args.output / "tfm_experimental.png", dpi=130)
    print(json.dumps({"shape": result.image.shape, "seconds": elapsed, "mapping_verified": result.mapping_verified, "timing_origin": result.timing_origin, "output": str(args.output)}))


if __name__ == "__main__":
    main()
