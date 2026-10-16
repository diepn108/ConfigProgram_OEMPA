"""Offline TFM controls and main-thread presentation; mathematics lives in oempa."""

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from oempa.dataset import AcquisitionDataset, AcquisitionMetadata, load_dataset
from oempa.probe import mapping_summary
from oempa.tfm import ImageGrid, LinearGeometry, TimingAssumption, TFMRequest, dataset_geometry, display_image, reconstruct, resolve_timing, save_result, validate_fmc
from ui.controller import OperationResult
from ui.state import Operation


@dataclass
class TFMViewState:
    source: AcquisitionDataset | None = None
    source_label: str = "No FMC source"
    revision: int = 0
    result: object = None
    result_revision: int | None = None
    source_is_current: bool = False
    source_detached: bool = False
    status: str = "Open an FMC dataset or select current acquired FMC."

    @property
    def stale(self):
        return self.result is not None and self.result_revision != self.revision


class TFMWorkspace:
    def __init__(self, app, parent):
        self.app = app
        self.state = TFMViewState()
        self.colorbar = None
        self._main_source_key = self.main_source_key()
        self._updating_source = False
        self.geometry_origin = "explicit user assumption"
        self.source_var = tk.StringVar(value="No FMC source")
        self.geometry_var = tk.StringVar(value="Active aperture comes from the FMC cube, not the full probe label.")
        self.status_var = tk.StringVar(value=self.state.status)
        self.provenance_var = tk.StringVar(value="")
        self.variables = {name: tk.StringVar(value=value) for name, value in (
            ("pitch", ""), ("velocity", ""), ("x_min", "-10"), ("x_max", "10"), ("z_min", "2"), ("z_max", "25"),
            ("x_count", "201"), ("z_count", "231"), ("sampling", ""), ("start", ""), ("method", "linear"), ("display", "normalized"))}
        ttk.Label(parent, text="Experimental TFM - Homogeneous medium").pack(anchor="w")
        ttk.Label(parent, text="Available signed callback MAX data; pre-compression RF / phase fidelity unverified.", wraplength=650).pack(anchor="w")
        source_controls = ttk.Frame(parent)
        source_controls.pack(fill="x", pady=4)
        self.open_button = ttk.Button(source_controls, text="Open FMC .npy", command=self.open_source)
        self.open_button.pack(side="left")
        self.current_button = ttk.Button(source_controls, text="Use current FMC", command=self.use_current)
        self.current_button.pack(side="left", padx=6)
        self.settings_visible = True
        self.settings_button = ttk.Button(source_controls, text="Hide settings", command=self.toggle_settings)
        self.settings_button.pack(side="left")
        self.save_button = ttk.Button(source_controls, text="Save result", command=self.save_result)
        self.save_button.pack(side="left", padx=6)
        self.status_label = ttk.Label(parent, textvariable=self.status_var, wraplength=650)
        self.status_label.pack(anchor="w")
        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True)
        self.parameters = ttk.Frame(body, width=260)
        self.parameters.pack(side="left", fill="y", padx=(0, 8))
        self.image_panel = ttk.Frame(body)
        self.image_panel.pack(side="left", fill="both", expand=True)
        self.reconstruct_button = ttk.Button(self.parameters, text="Reconstruct TFM (offline)", command=self.start_reconstruction)
        self.reconstruct_button.pack(side="bottom", fill="x", pady=4)
        scroll = ttk.Scrollbar(self.parameters, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.settings_canvas = tk.Canvas(self.parameters, width=250, highlightthickness=0, yscrollcommand=scroll.set)
        self.settings_canvas.pack(side="left", fill="both", expand=True)
        scroll.configure(command=self.settings_canvas.yview)
        controls = ttk.Frame(self.settings_canvas, padding=(0, 0, 6, 0))
        window = self.settings_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda event: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")))
        self.settings_canvas.bind("<Configure>", lambda event: self.settings_canvas.itemconfigure(window, width=event.width))
        def wheel(event):
            self.settings_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"
        self.settings_canvas.bind("<MouseWheel>", wheel)
        input_group = ttk.LabelFrame(controls, text="TFM Input", padding=6)
        input_group.pack(fill="x", pady=(0, 4))
        ttk.Label(input_group, textvariable=self.source_var, wraplength=215).pack(anchor="w")
        ttk.Label(input_group, textvariable=self.geometry_var, wraplength=215).pack(anchor="w", pady=4)
        self.input_group = input_group
        propagation = ttk.LabelFrame(controls, text="Propagation", padding=6)
        propagation.pack(fill="x", pady=4)
        ttk.Label(propagation, text="Model: Homogeneous medium").grid(row=0, column=0, columnspan=2, sticky="w")
        region = ttk.LabelFrame(controls, text="Image region", padding=6)
        region.pack(fill="x", pady=4)
        resolution = ttk.LabelFrame(controls, text="Resolution", padding=6)
        resolution.pack(fill="x", pady=4)
        legacy_group = ttk.LabelFrame(controls, text="Missing timing only", padding=6)
        legacy_group.pack(fill="x", pady=4)
        self.entries = {}
        fields = (("pitch", "Pitch (mm)", input_group, 2), ("velocity", "Velocity (m/s)", propagation, 1),
                  ("x_min", "X min (mm)", region, 0), ("x_max", "X max (mm)", region, 1),
                  ("z_min", "Z min (mm)", region, 2), ("z_max", "Z max (mm)", region, 3),
                  ("x_count", "X pixels", resolution, 0), ("z_count", "Z pixels", resolution, 1),
                  ("sampling", "Rate (MHz)", legacy_group, 0), ("start", "Start (us)", legacy_group, 1))
        # Input labels/entries use a separate grid frame to preserve pack ownership.
        pitch_row = ttk.Frame(input_group)
        pitch_row.pack(fill="x")
        for name, label, group, row in fields:
            group = pitch_row if name == "pitch" else group
            row = 0 if name == "pitch" else row
            ttk.Label(group, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
            entry = ttk.Entry(group, textvariable=self.variables[name], width=9)
            entry.grid(row=row, column=1, sticky="e", pady=2)
            self.entries[name] = entry
        self.water_button = ttk.Button(propagation, text="Water example: 1480 m/s", command=lambda: self.variables["velocity"].set("1480"))
        self.water_button.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        self.selectors = {}
        for column, (name, values) in enumerate((("method", ("nearest", "linear")), ("display", ("raw", "absolute", "normalized", "db")))):
            parent_frame = resolution if name == "method" else source_controls
            label = ttk.Label(parent_frame, text="Method" if name == "method" else "Display")
            selector = ttk.Combobox(parent_frame, textvariable=self.variables[name], values=values, state="readonly", width=10)
            if name == "method":
                label.grid(row=2, column=0, sticky="w")
                selector.grid(row=2, column=1)
            else:
                label.pack(side="left", padx=6)
                selector.pack(side="left")
            self.selectors[name] = selector
        ttk.Label(controls, text="Display processing only: normalized = abs(I) / image peak. Out-of-window paths contribute zero.", wraplength=215).pack(anchor="w", pady=4)
        ttk.Label(controls, textvariable=self.provenance_var, wraplength=215).pack(anchor="w")
        for name, variable in self.variables.items():
            variable.trace_add("write", self._display_edited if name == "display" else lambda *args, key=name: self._request_edited(key))
        def bind_scroll(widget):
            widget.bind("<MouseWheel>", wheel)
            for child in widget.winfo_children():
                bind_scroll(child)
        bind_scroll(controls)

    def toggle_settings(self, visible=None):
        self.settings_visible = not self.settings_visible if visible is None else visible
        if self.settings_visible:
            self.parameters.pack(side="left", fill="y", padx=(0, 8), before=self.image_panel)
        else:
            self.parameters.pack_forget()
        self.settings_button.configure(text="Hide settings" if self.settings_visible else "Show settings")

    def _request_edited(self, name=None):
        if self._updating_source:
            return
        if name == "pitch":
            self.geometry_origin = "explicit user pitch override/assumption"
        self.state.revision += 1
        if self.state.result is not None:
            self.state.status = "STALE - reconstruction assumptions/source changed; reconstruct again."
            self.show_result()
        self.refresh()

    def _display_edited(self, *args):
        if self.state.result is not None:
            self.show_result()

    def read_request(self):
        if self.state.source is None:
            raise ValueError("TFM requires FMC data: use current FMC or open an offline cube.")
        if self.state.source_detached:
            raise ValueError("FMC source replaced; select Use current FMC or open an offline cube.")
        source = self.state.source
        try:
            geometry = LinearGeometry(source.data.shape[0], float(self.variables["pitch"].get()) * 1e-3)
        except ValueError:
            raise ValueError("Enter a finite positive element pitch in mm.") from None
        grid = ImageGrid(float(self.variables["x_min"].get()) * 1e-3, float(self.variables["x_max"].get()) * 1e-3, int(self.variables["x_count"].get()),
                         float(self.variables["z_min"].get()) * 1e-3, float(self.variables["z_max"].get()) * 1e-3, int(self.variables["z_count"].get()))
        timing = None if source.metadata.complete else TimingAssumption(float(self.variables["sampling"].get()) * 1e6, float(self.variables["start"].get()) * 1e-6)
        try:
            velocity = float(self.variables["velocity"].get())
        except ValueError:
            raise ValueError("Enter a propagation velocity in m/s (e.g. water example 1480).") from None
        request = TFMRequest(geometry, velocity, grid, self.variables["method"].get(), timing, self.geometry_origin)
        request.validate(source, check_samples=False)
        return request

    def main_source_key(self):
        data = self.app.fmc_data
        return None if data is None else (id(data.data), getattr(data.metadata, "configuration_revision", None))

    def refresh_geometry(self):
        source = self.state.source
        if source is None:
            return
        count = source.data.shape[0]
        description = source.metadata.probe.description
        probe_count = dict(description.values).get("elements", "unknown") if description is not None else "unknown"
        text = f"Active elements: {count}; full probe label: {probe_count}\n"
        try:
            geometry = LinearGeometry(count, float(self.variables["pitch"].get()) * 1e-3)
            positions = geometry.positions_m * 1e3
            text += f"Span: {positions[-1] - positions[0]:g} mm ({positions[0]:g} to {positions[-1]:g})\n"
        except (ValueError, OverflowError):
            text += "Pitch required; no geometry assumed.\n"
        probe = source.metadata.probe
        if probe.logical_to_physical is not None and len(probe.logical_to_physical) >= count:
            mapping = probe.logical_to_physical[:count]
            elements = f"{mapping[0]}-{mapping[-1]}" if mapping == tuple(range(mapping[0], mapping[0] + count)) else str(mapping)
            text += f"Mapping: logical 0-{count - 1} -> elements {elements}\nSource: {probe.mapping_source or 'unspecified source'}\n"
        else:
            text += "Probe/channel mapping: Unverified\n"
        origin = "dataset metadata" if self.geometry_origin.startswith("Dataset probe metadata") else "explicit user assumption" if self.geometry_origin.startswith("explicit user") else "unavailable/invalid"
        text += f"Physical wiring: {probe.physical_wiring_validation}\nPitch source: {origin}"
        self.geometry_var.set(text)

    def refresh(self):
        key = self.main_source_key()
        if key != self._main_source_key:
            self._main_source_key = key
            if self.state.source is not None:
                self.state.revision += 1
                self.state.source_detached = self.state.source_is_current
                self.state.status = "FMC dataset changed; select input/reconstruct. Previous image is STALE."
                if self.state.result is not None:
                    self.show_result()
        self.refresh_geometry()
        editable = self.app.state.editable and not self.app.controller.active
        legacy = self.state.source is not None and not self.state.source.metadata.complete
        for name, entry in self.entries.items():
            entry.configure(state="normal" if editable and (name not in {"sampling", "start"} or legacy) else "disabled")
        for selector in self.selectors.values():
            selector.configure(state="readonly" if editable else "disabled")
        self.open_button.configure(state="normal" if editable else "disabled")
        self.settings_button.configure(state="normal" if editable else "disabled")
        self.save_button.configure(state="normal" if editable and self.state.result is not None else "disabled")
        self.water_button.configure(state="normal" if editable else "disabled")
        self.current_button.configure(state="normal" if editable and self.app.fmc_data is not None else "disabled")
        try:
            self.read_request()
            valid, reason = True, ""
        except (ValueError, OverflowError, tk.TclError) as exc:
            valid, reason = False, str(exc) or "Enter valid pitch, velocity, grid and required legacy timing assumptions."
        self.reconstruct_button.configure(state="normal" if editable and valid else "disabled")
        status = self.state.status
        if self.state.stale and "STALE" not in status:
            status = "STALE - reconstruction assumptions/source changed. | " + status
        if self.state.source_is_current and (self.app.state.dataset_stale or self.app.fmc_data is None or self.app.fmc_data.data is not self.state.source.data):
            status += " | FMC source is historical/stale relative to the current hardware draft/dataset."
        self.status_var.set(status + (f" | {reason}" if reason and not self.app.controller.active else ""))

    def accept_source(self, source, label, current=False):
        validate_fmc(source)
        if source.metadata.complete:
            resolve_timing(source)
        self.state.source = source
        self.state.source_label = label
        self.state.source_is_current = current
        self.state.source_detached = False
        self._main_source_key = self.main_source_key()
        self.state.revision += 1
        metadata = source.metadata
        # Each source owns its pitch/timing; never carry another dataset's manual values.
        try:
            geometry, origin = dataset_geometry(source)
        except ValueError as exc:
            geometry, origin = None, str(exc)
        self._updating_source = True
        try:
            self.variables["pitch"].set(f"{geometry.pitch_m * 1e3:g}" if geometry is not None else "")
            self.variables["sampling"].set("")
            self.variables["start"].set("")
            self.geometry_origin = origin
        finally:
            self._updating_source = False
        description = f"{Path(label).name}\nFMC shape: {source.data.shape} | {source.data.dtype}\nAcquisition Rev {metadata.configuration_revision}"
        if metadata.complete:
            timing, origin = resolve_timing(source)
            description += f" | {timing.sampling_hz / 1e6:g} MHz / start {timing.start_s * 1e6:g} us (captured)"
        else:
            description += " | Metadata incomplete; explicit rate AND start assumptions required."
        self.source_var.set(description)
        self.state.status = "Source loaded offline; geometry/material assumptions required."
        if self.state.result is not None:
            self.show_result()
        self.refresh()

    def use_current(self):
        if not self.app.state.editable or self.app.controller.active or self.app.fmc_data is None:
            return
        data = self.app.fmc_data
        metadata = data.metadata or AcquisitionMetadata("FMC", data.shape, data.data.dtype.str, axis_names=("TX", "RX", "sample"), warnings=("Current FMC lacks captured metadata.",))
        try:
            label = "Current FMC" if not self.app.state.dataset_stale else "Offline/historical FMC in viewer"
            self.accept_source(AcquisitionDataset(data.data, metadata), label, current=True)
        except ValueError as exc:
            self.state.status = str(exc)
            self.refresh()

    def open_source(self):
        if not self.app.state.editable or self.app.controller.active:
            return
        path = filedialog.askopenfilename(title="Open FMC for offline TFM", initialdir=Path(__file__).resolve().parents[1] / "data", filetypes=[("NumPy FMC", "*.npy")])
        if path:
            self.load_source(path)

    def load_source(self, path):
        label = str(path)
        def task(context):
            context.check_cancelled()
            source = load_dataset(label)
            validate_fmc(source)
            context.check_cancelled()
            return OperationResult(payload=(source, label), status="FMC source loaded offline")
        self.app.controller.submit(Operation.LOADING, task)
        self.state.status = "Loading FMC offline..."
        self.app._set_busy(True)

    def start_reconstruction(self):
        if not self.app.state.editable or self.app.controller.active:
            return
        try:
            request = self.read_request()
            source, label, revision = self.state.source, self.state.source_label, self.state.revision
            def task(context):
                result = reconstruct(source, request, source_label=label, cancel_check=context.check_cancelled, progress=context.progress)
                return OperationResult(payload=(result, revision), status="Offline TFM completed; physical validation excluded")
            self.app.controller.submit(Operation.RECONSTRUCTING, task)
            self.state.status = "Reconstructing offline..."
            self.app.progress_var.set(0)
            self.app.progress_text_var.set("0 / image pixels")
            self.app._set_busy(True)
        except (ValueError, RuntimeError, OverflowError) as exc:
            self.state.status = str(exc)
            self.refresh()

    def save_result(self):
        if not self.app.state.editable or self.app.controller.active or self.state.result is None:
            return
        path = filedialog.asksaveasfilename(title="Save experimental TFM numerical result + metadata", defaultextension=".npz", filetypes=[("TFM result with embedded JSON", "*.npz")])
        if not path:
            return
        result = self.state.result
        def task(context):
            context.check_cancelled()
            save_result(path, result)
            return OperationResult(payload={"tfm_saved": str(path)}, status="TFM result saved offline")
        self.app.controller.submit(Operation.LOADING, task)
        self.state.status = "Saving unnormalized TFM result offline..."
        self.app._set_busy(True)

    def handle_event(self, event):
        if event.kind == "completed" and not self.app.state.closing:
            if event.operation == Operation.LOADING:
                payload = event.payload.payload
                if isinstance(payload, dict) and "tfm_saved" in payload:
                    self.state.status = "TFM numerical result and metadata saved offline."
                    self.app.log(f"[OFFLINE] TFM result saved: {payload['tfm_saved']}")
                else:
                    self.accept_source(*payload)
                    self.app.log(f"[OFFLINE] FMC source loaded for TFM: {self.state.source_label}")
            else:
                self.state.result, self.state.result_revision = event.payload.payload
                self.state.status = "Experimental/unverified TFM - features are not identified as defects."
                self.toggle_settings(False)
                self.show_result()
                self.app.log(f"[OFFLINE] TFM {self.state.result.method} completed; probe/channel mapping unverified")
        elif event.kind in {"error", "cancelled"}:
            self.state.status = f"Offline {event.operation.value} {event.kind}: {event.payload}"
        self.refresh()

    def show_result(self):
        result = self.state.result
        if result is None:
            return
        view = display_image(result, self.variables["display"].get())
        figure, axes, canvas = self.app.plots["TFM"]
        axes.clear()
        mesh = axes.pcolormesh(result.x_m * 1e3, result.z_m * 1e3, view.values, shading="auto", cmap=view.cmap, vmin=view.vmin, vmax=view.vmax)
        axes.set_xlim(result.x_m[0] * 1e3, result.x_m[-1] * 1e3)
        axes.set_ylim(result.z_m[-1] * 1e3, result.z_m[0] * 1e3)
        axes.set_aspect("equal", adjustable="box")
        axes.set_xlabel("Lateral position (mm)")
        axes.set_ylabel("Depth (mm)")
        axes.set_title(f"Experimental TFM - Homogeneous Medium\nc = {result.velocity_m_s:g} m/s" + (" | STALE assumptions/source" if self.state.stale else ""), fontsize=9)
        if self.colorbar is None:
            self.colorbar = figure.colorbar(mesh, ax=axes, fraction=.04, pad=.02, aspect=30)
        else:
            self.colorbar.update_normal(mesh)
        label = {"raw": "Signed sum", "absolute": "Absolute sum", "normalized": "|I| / peak", "db": "dB re peak"}[self.variables["display"].get()]
        self.colorbar.set_label(label + " (display only)", fontsize=8)
        self.provenance_var.set(f"Image source: {Path(result.source_label).name} | Rev {result.configuration_revision} | {result.method} | pitch {result.request.geometry.pitch_m * 1e3:g} mm / velocity {result.request.velocity_m_s:g} m/s (assumed)\n{result.sampling_hz / 1e6:g} MHz / start {result.start_s * 1e6:g} us - {result.timing_origin}; Probe/channel mapping: Unverified\n{mapping_summary(result.source_metadata.probe)}; physical wiring: {result.source_metadata.probe.physical_wiring_validation}\nDisplay processing only; coherent signed image retained. z=0 is the array reference plane.")
        # Equal-aspect axes need compressed layout to center the image/colorbar group.
        figure.set_layout_engine("compressed")
        canvas.draw_idle()
