import math
import time
from dataclasses import replace
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from oempa.bscan import BScanProcessor
from oempa.fmc import FMCData
from oempa.config import FMCConfig
from oempa.ascan_config import SingleElementAscanConfig
from oempa.dataset import ProbeProvenance, save_dataset
from oempa.probe import PROBE_DEFAULTS, ProbeDescription, DOCUMENTED_MAPPING, MAPPING_SOURCE, mapping_summary
from ui.diagnostics import DiagnosticHistory, append_visible_log
from ui.fmc_inspection import display_traces
from oempa.gui_backend import GUIBackend
from ui.controller import OperationController, OperationResult
from ui.layout import build_layout
from ui.presentation import dataset_summary, display_text, status_summary
from oempa.focal_law import FocalLawCalculator
from oempa.verified_pa import inspect_approved_pa
from oempa.verified_fmc import inspect_approved_fmc
from ui.state import ApplicationState, ConnectionState, Operation


# Paths

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_DIR / "configs"
DATA_DIR = PROJECT_DIR / "data"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

GUI_CONFIG_PATH = CONFIG_DIR / "gui_fmc_config.txt"


class OEMPAGUI:
    def __init__(self, root):
        self.root = root

        self.root.title(
            "AOS OEM-PA Configuration & Acquisition"
        )

        self.root.geometry("1300x820")
        self.root.minsize(1100, 700)

        # Backend

        self.state = ApplicationState(hardware_modes=frozenset({"FMC", "A-scan"}))
        self.controller = OperationController(self.state)
        self.backend = GUIBackend(GUI_CONFIG_PATH)
        self._applied_config = None
        self._destroyed = False
        self.ascan_data = None
        self.fmc_data = None
        self.bscan_data = None

        self.busy = False
        self.diagnostic_history = DiagnosticHistory()
        self._visible_log_lines = 0

        # Tk variables

        self.ip_var = tk.StringVar(
            value="192.168.1.11"
        )

        self.port_var = tk.StringVar(
            value="5001"
        )

        self.tx_count_var = tk.StringVar(
            value="16"
        )

        self.rx_count_var = tk.StringVar(
            value="16"
        )

        self.range_var = tk.StringVar(
            value="30.0"
        )

        self.analog_gain_var = tk.StringVar(
            value="20.0"
        )

        self.digital_gain_var = tk.StringVar(
            value="0.0"
        )

        self.pulser_width_var = tk.StringVar(
            value="0.5"
        )

        self.filter_var = tk.StringVar(
            value="1"
        )

        self.time_slot_var = tk.StringVar(
            value="2000.0"
        )

        self.tx_view_var = tk.IntVar(
            value=0
        )

        self.rx_view_var = tk.IntVar(
            value=0
        )

        self.view_mode_var = tk.StringVar(
            value="A-Scan"
        )

        self.bscan_display_var = tk.StringVar(
            value="Absolute"
        )
        self.fmc_trace_view_var = tk.StringVar(value="Individual TX/RX")
        self.fmc_diagonal_normalization_var = tk.StringVar(value="Per trace")
        self.bscan_normalization_var = tk.StringVar(value="Global")
        self.bscan_contrast_var = tk.StringVar(value="Linear")
        self.inspection_status_var = tk.StringVar(value="Display processing only; raw FMC data unchanged")

        self.bscan_gate_start_var = tk.StringVar(
            value="2.0"
        )

        self.bscan_gate_end_var = tk.StringVar(
            value="30.0"
        )

        self.connection_status_var = (
            tk.StringVar(
                value="Disconnected"
            )
        )

        self.cycle_status_var = (
            tk.StringVar(
                value="--"
            )
        )

        self.multichannel_status_var = (
            tk.StringVar(
                value="--"
            )
        )

        self.data_shape_var = tk.StringVar(
            value="--"
        )

        self.data_min_var = tk.StringVar(
            value="--"
        )

        self.data_max_var = tk.StringVar(
            value="--"
        )

        self.progress_var = tk.DoubleVar(
            value=0.0
        )

        self.progress_text_var = (
            tk.StringVar(
                value="0 / 0"
            )
        )

        self.header_var = tk.StringVar(value="")
        self.dataset_summary_var = tk.StringVar(value="No dataset")
        self.stale_var = tk.StringVar(value="")
        self.warning_var = tk.StringVar(value="")
        self.readback_var = tk.StringVar(value="Unavailable")
        self.ascan_vars = {key: tk.StringVar(value="0") for key in ("tx", "rx", "start", "tx_delay", "rx_delay")}
        self.mode_var = tk.StringVar(value="FMC")
        self.mode_help_var = tk.StringVar(value="FMC MultiHWChannel acquisition/replay")
        self.probe_vars = {key: tk.StringVar(value=value) for key, value in PROBE_DEFAULTS.items()}
        self.probe_metadata = self._read_probe_metadata()
        self.pa_vars = {key: tk.StringVar(value=value) for key, value in (("start", "0"), ("count", "16"), ("angle", "0"), ("pitch", ""), ("velocity", ""))}
        self.pa_summary_var = tk.StringVar(value="Enter pitch and velocity assumptions to calculate. No hardware action.")
        self.pa_law = None

        # UI

        self._build_ui()

        self.mode_var.trace_add("write", lambda *args: self.change_mode())
        for variable in self._configuration_variables():
            variable.trace_add("write", self._configuration_edited)
        self._configuration_edited()
        for variable in self.probe_vars.values():
            variable.trace_add("write", self._probe_edited)
        for variable in self.pa_vars.values():
            variable.trace_add("write", self._pa_preview_edited)
        self.root.after(25, self._consume_events)

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close,
        )

        self.log(
            "OEM-PA application ready."
        )

    # UI construction

    def _build_ui(self):
        build_layout(self)

    def change_mode(self, event=None):
        self.state.set_mode({"Phased Array": "PA"}.get(self.mode_var.get(), self.mode_var.get()))
        self.mode_help_var.set("FMC MultiHWChannel acquisition/replay" if self.state.mode == "FMC" else "Acquisition mode is separate from the display tab." if self.state.mode == "A-scan" else "Offline viewing / preview only; hardware apply and acquisition unavailable")
        if hasattr(self, "fmc_settings"):
            self.fmc_settings.grid() if self.state.mode == "FMC" else self.fmc_settings.grid_remove()
        if hasattr(self, "mode_help_label"):
            self.mode_help_label.grid_remove() if self.state.mode == "FMC" else self.mode_help_label.grid()
        if hasattr(self, "ascan_settings"):
            self.ascan_settings.grid() if self.state.mode == "A-scan" else self.ascan_settings.grid_remove()
        if hasattr(self, "pa_settings"):
            self.pa_settings.grid() if self.state.mode == "PA" else self.pa_settings.grid_remove()
        if hasattr(self, "start_entry"):
            if self.state.mode == "A-scan":
                self.start_fixed.grid_remove()
                self.start_entry.grid()
            else:
                self.start_entry.grid_remove()
                self.start_fixed.grid()
        self._configuration_edited()

    def change_display(self, event=None):
        name = self.workspace.tab(self.workspace.select(), "text")
        if name in self.plots:
            self.figure, self.axes, self.canvas = self.plots[name]
        if name in {"A-scan", "FMC", "B-scan"}:
            self.view_mode_var.set("B-Scan" if name == "B-scan" else "A-Scan")
            self.update_data_view()

    def stop_operation(self):
        self.controller.cancel()
        self._set_busy(False)

    def _read_probe_metadata(self):
        description = ProbeDescription.from_values({key: variable.get() for key, variable in self.probe_vars.items()})
        values = dict(description.values)
        span = 15 * float(values['pitch']) if values['pitch'] == '0.6' else None
        return ProbeProvenance(identity=self.probe_vars["full_marking"].get() or None, description=description,
                               logical_to_physical=DOCUMENTED_MAPPING, mapping_source=MAPPING_SOURCE,
                               usable_element_count=16, aperture_span_mm=span)

    def _probe_edited(self, *args):
        self.probe_metadata = self._read_probe_metadata()

    def _pa_preview_edited(self, *args):
        self.pa_law = None
        self.pa_summary_var.set("Preview assumptions changed; recalculate offline law.")
        if hasattr(self, "plots"):
            figure, axes, canvas = self.plots["Phased Array"]
            axes.clear()
            axes.set_title("Preview assumptions changed; recalculate")
            canvas.draw_idle()

    def preview_pa(self):
        try:
            start = int(self.pa_vars["start"].get())
            count = int(self.pa_vars["count"].get())
            angle = float(self.pa_vars["angle"].get())
            pitch = float(self.pa_vars["pitch"].get())
            velocity = float(self.pa_vars["velocity"].get())
            if not all(math.isfinite(value) for value in (angle, pitch, velocity)) or not -90 < angle < 90:
                raise ValueError("Enter finite assumptions and an angle between -90 and 90 degrees.")
            law = FocalLawCalculator(16, pitch, velocity).steering_delays(angle, start, count)
            self.pa_law = law
            figure, axes, canvas = self.plots["Phased Array"]
            axes.clear()
            axes.plot(law.element_indices, law.tx_delays_us, "o-", label="TX (4 ns quantization)")
            axes.plot(law.element_indices, law.rx_delays_us, "x-", label="RX (5 ns quantization)")
            axes.set_xlabel("Logical element (mapping unverified)")
            axes.set_ylabel("Delay (us)")
            axes.legend()
            axes.grid(True, alpha=0.25)
            figure.set_layout_engine("tight")
            canvas.draw_idle()
            self.pa_summary_var.set(f"Offline {count}-element law at {angle:g} deg | TX delay span {np.ptp(law.tx_delays_us):.3f} us | RX delay span {np.ptp(law.rx_delays_us):.3f} us")
        except (ValueError, OverflowError) as exc:
            self.pa_law = None
            if hasattr(self, "plots"):
                figure, axes, canvas = self.plots["Phased Array"]
                axes.clear()
                axes.set_title("Invalid preview assumptions")
                canvas.draw_idle()
            self.pa_summary_var.set(str(exc))

    def _refresh_presentation(self):
        self.header_var.set(status_summary(self.state))
        summary = dataset_summary(self.fmc_data) if self.ascan_data is None else self._ascan_summary()
        if self.fmc_data is not None and self.ascan_data is None:
            summary += "\nAll diagonal TX=RX traces; logical channels only" if self.fmc_trace_view_var.get() == "All diagonal traces" else f"\nSelected: TX {self.tx_view_var.get()} / RX {self.rx_view_var.get()}"
        self.dataset_summary_var.set(summary)
        self.stale_var.set("STALE - configuration changed after acquisition" if self.state.dataset_stale else "")
        notice = "FMC classification / base TX width and delay: Applied configuration verified; hardware readback unavailable (AOS SDK limitation)" if self.state.configuration_verified and not self.state.readback_verified else ""
        self.warning_var.set(display_text(self.state.error or "\n".join(self.state.verification_mismatches[:2]) or notice or self.state.status)[:700])
        snapshot = self.state.actual_snapshot
        if hasattr(self, "fmc_expected_var"):
            n = snapshot.cycles[0].point_count if snapshot is not None and snapshot.mode == "FMC" and snapshot.cycles and self.state.configuration_verified else "N"
            self.fmc_expected_var.set(f"Expected Dataset\nRaw: 256 x {n}\nFMC: 16 x 16 x {n}\nN from current verified readback")
        if snapshot is None or not snapshot.cycles:
            self.readback_var.set("Start / range / point count / sampling / representation: unavailable")
        else:
            cycle = snapshot.cycles[0]
            def value(number, scale=1, unit=""):
                return "unavailable" if number is None else f"{number * scale:g} {unit}".strip()
            representation = "Signed" if cycle.rectification == 0 else "Rectification enum " + str(cycle.rectification)
            bits = {0: "8-bit", 1: "12-bit", 2: "16-bit"}.get(cycle.bit_size, "unavailable")
            compression = {0: "Compression", 1: "Decimation"}.get(cycle.compression_type, "unavailable")
            self.readback_var.set(f"Start / range: {value(cycle.start_s, 1e6, 'us')} / {value(cycle.range_s, 1e6, 'us')}\nSampling: {value(cycle.sampling_hz, 1e-6, 'MHz')}\nSamples: {cycle.point_count}\nRepresentation: {representation} {bits}\nCompression: {compression}")


    # Connection

    def connect_device(self):
        if self.busy or self.state.closing:
            return
        try:
            ip_address = self.ip_var.get().strip()
            port = int(self.port_var.get())
            if ip_address != "192.168.1.11" or port != 5001:
                raise ValueError("Use the established OEM-PA endpoint 192.168.1.11:5001.")
            self.controller.submit(Operation.CONNECTING, lambda context: self.backend.connect(context, ip_address, port))
        except Exception as exc:
            self._operation_error("Connection failed", exc)
            return
        self.log("Connecting to OEM-PA...")
        self._set_busy(True)

    def _connect_success(self, status):
        self.connection_status_var.set("Connected")
        self.cycle_status_var.set(str(status["cycle_count"]))
        supported = status["multichannel_supported"]
        enabled = status["multichannel_enabled"]
        text = "Supported / Enabled" if supported and enabled else "Supported / Disabled" if supported else "Not Supported"
        self.multichannel_status_var.set(text)
        self.log(f"[OK] Connected; cycle count: {status['cycle_count']}; Multi-Channel: {text}")
        self.log("Apply the draft configuration before acquiring.")
        self._set_busy(False)

    def disconnect_device(self):
        if self.busy or self.state.closing:
            return
        self.controller.submit(Operation.DISCONNECTING, self.backend.close)
        self.log("Disconnecting...")
        self._set_busy(True)

    def _disconnect_success(self):
        self.ascan_data = None
        self._applied_config = None
        self.fmc_data = None
        self.bscan_data = None
        self.data_shape_var.set("--")
        self.data_min_var.set("--")
        self.data_max_var.set("--")
        self.progress_var.set(0.0)
        self.progress_text_var.set("0 / 0")
        self.connection_status_var.set("Disconnected")
        self.cycle_status_var.set("--")
        self.multichannel_status_var.set("--")
        self.axes.clear()
        self.axes.set_title("No FMC data")
        self.canvas.draw_idle()
        self.log("[OK] Disconnected")
        self._set_busy(False)

    # Configuration actions

    def _read_configuration(self):
        try:
            if self.state.mode == "A-scan":
                config = SingleElementAscanConfig(tx_element=int(self.ascan_vars["tx"].get()), rx_element=int(self.ascan_vars["rx"].get()),
                    tx_delay_us=float(self.ascan_vars["tx_delay"].get()), rx_delay_us=float(self.ascan_vars["rx_delay"].get()),
                    start_us=float(self.ascan_vars["start"].get()), range_us=float(self.range_var.get()),
                    analog_gain_db=float(self.analog_gain_var.get()), digital_gain_db=float(self.digital_gain_var.get()),
                    pulser_width_us=float(self.pulser_width_var.get()), filter_index=int(self.filter_var.get()), time_slot_us=float(self.time_slot_var.get()))
                config.validate()
                return config
            config = FMCConfig(
                tx_count=int(
                    self.tx_count_var.get()
                ),
                rx_count=int(
                    self.rx_count_var.get()
                ),
                range_us=float(
                    self.range_var.get()
                ),
                time_slot_us=float(
                    self.time_slot_var.get()
                ),
                analog_gain_db=float(
                    self.analog_gain_var.get()
                ),
                digital_gain_db=float(
                    self.digital_gain_var.get()
                ),
                beam_correction_db=0.0,
                filter_index=int(
                    self.filter_var.get()
                ),
                pulser_width_us=float(
                    self.pulser_width_var.get()
                ),
            )

            config.validate()
            values = (config.range_us, config.time_slot_us, config.analog_gain_db,
                      config.digital_gain_db, config.pulser_width_us)
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Configuration values must be finite numbers.")

            return config

        except ValueError as exc:
            raise ValueError(
                f"Invalid configuration: {exc}"
            ) from exc

    def apply_configuration(self):
        if self.busy or self.state.closing:
            return
        try:
            selected = {"Phased Array": "PA"}.get(self.mode_var.get(), self.mode_var.get())
            if selected != self.state.mode:
                self.change_mode()
            if self.state.mode not in {"FMC", "A-scan"}:
                raise ValueError("Generated configuration application supports FMC and single-element A-scan only.")
            config = self._read_configuration()
            self.state.draft_valid = True
            self.controller.submit(Operation.APPLYING, lambda context: self.backend.apply(context, config))
        except Exception as exc:
            self._operation_error("Configuration failed", exc)
            return
        self.log(f"[INFO] Applying {self.state.mode} configuration...")
        self._mark_stale_data()
        self._set_busy(True)

    def apply_approved_fmc_file(self, path):
        """Explicit existing-file acceptance entry point; no file generation."""
        if self.busy or self.state.closing:
            return
        config = inspect_approved_fmc(path)
        self.mode_var.set("FMC")
        self.state.set_mode("FMC")
        for variable, value in ((self.tx_count_var, config.tx_count), (self.rx_count_var, config.rx_count), (self.range_var, config.range_us), (self.time_slot_var, config.time_slot_us), (self.analog_gain_var, config.analog_gain_db), (self.digital_gain_var, config.digital_gain_db), (self.pulser_width_var, config.pulser_width_us), (self.filter_var, config.filter_index)):
            variable.set(str(value))
        self.state.draft_valid = True
        self.controller.submit(Operation.APPLYING, lambda context: self.backend.apply_approved_fmc_file(context, path))
        self.log(f"Applying unchanged FMC file: {Path(path).name}; acquisition OFF")
        self._set_busy(True)

    def apply_approved_pa_file(self, path):
        """Explicit existing-file acceptance entry point; no PA acquisition."""
        if self.busy or self.state.closing:
            return
        config = inspect_approved_pa(path)
        self.mode_var.set("Phased Array")
        self.state.set_mode("PA")
        for variable, value in ((self.tx_count_var, config.element_count), (self.rx_count_var, config.element_count), (self.range_var, config.range_us), (self.time_slot_var, config.time_slot_us), (self.analog_gain_var, config.analog_gain_db), (self.digital_gain_var, config.digital_gain_db), (self.pulser_width_var, config.pulser_width_us), (self.filter_var, config.filter_index)):
            variable.set(str(value))
        self.state.configuration_modes = frozenset({"FMC", "PA"})
        self.state.draft_valid = True
        self.controller.submit(Operation.APPLYING, lambda context: self.backend.apply_approved_pa_file(context, path))
        self.log(f"Applying existing approved PA file: {Path(path).name}; acquisition OFF")
        self._set_busy(True)

    def _apply_config_success(
        self,
        config,
        status,
    ):
        if isinstance(config, SingleElementAscanConfig):
            self._applied_config = config
            self.cycle_status_var.set(str(status["cycle_count"]))
            self.multichannel_status_var.set("Disabled")
            self.log("[OK] Single-element A-scan readback verified; acquisition OFF")
            self._log_readback()
            self._set_busy(False)
            return
        if self.state.applied_mode == "PA":
            self.state.configuration_modes = None
            self.cycle_status_var.set(str(status["cycle_count"]))
            self.multichannel_status_var.set("Supported / Enabled" if status["multichannel_enabled"] else "Supported / Disabled" if status["multichannel_supported"] else "Not Supported")
            self._applied_config = config
            self.log("[OK] Existing PA file applied; readback verified; PA acquisition unsupported")
            self.log(f"Readback scope: {self.state.verification_scope}")
            self._log_readback()
            self.log("[SAFE] Acquisition remains OFF")
            self._set_busy(False)
            return
        self.cycle_status_var.set(
            str(
                status["cycle_count"]
            )
        )

        self.multichannel_status_var.set(
            "Supported / Enabled"
        )

        self.tx_spinbox.configure(
            to=max(
                0,
                config.tx_count - 1,
            )
        )

        self.rx_spinbox.configure(
            to=max(
                0,
                config.rx_count - 1,
            )
        )

        self._applied_config = config
        self.log("[OK] Configuration applied")
        self.log(f"Readback scope: {self.state.verification_scope}")
        self._log_readback()

        self.log(
            f"TX: {config.tx_count}, "
            f"RX: {config.rx_count}, "
            f"cycles: {config.cycle_count}"
        )

        self.log(
            "[SAFE] Acquisition remains OFF"
        )

        self._set_busy(
            False
        )

    # Acquisition actions

    def acquire_fmc(self):
        if self.busy or self.state.closing:
            return
        if not self.state.acquisition_ready:
            messagebox.showwarning("Configuration Not Ready", "Connect and apply a valid configuration with successful readback before acquiring.")
            return
        config = self._applied_config
        probe = self.probe_metadata
        self._fmc_requested_at = time.perf_counter()
        self.controller.submit(Operation.ACQUIRING, lambda context: self.backend.acquire(context, config, probe))
        self.progress_var.set(0.0)
        self.progress_text_var.set(f"0 / {config.cycle_count}")
        self.log(f"[INFO] Starting {self.state.mode} acquisition...")
        self._set_busy(True)

    def _update_progress(
        self,
        received,
        total,
    ):
        if total > 0:
            percent = (
                received
                / total
                * 100.0
            )
        else:
            percent = 0.0

        self.progress_var.set(
            percent
        )

        self.progress_text_var.set(
            f"{received} / {total}"
        )

    def _acquisition_success(
        self,
        fmc_data,
    ):
        if getattr(getattr(fmc_data, "metadata", None), "mode", None) == "A-scan":
            self.ascan_data = fmc_data
            self.fmc_data = None
            self.bscan_data = None
            for name in ("FMC", "B-scan"):
                figure, axes, canvas = self.plots[name]
                axes.clear()
                axes.set_title("No FMC dataset; single-element A-scan available in A-scan tab")
                canvas.draw_idle()
            self.progress_var.set(100.0)
            self.progress_text_var.set("1 / 1")
            self.data_shape_var.set(str(fmc_data.data.shape))
            self.data_min_var.set(str(int(fmc_data.data.min())))
            self.data_max_var.set(str(int(fmc_data.data.max())))
            self.workspace.select(self.workspace.tabs()[0])
            self.view_mode_var.set("A-Scan")
            self.log("[OK] A-scan acquisition complete")
            self.log(self._ascan_summary())
            self.log(f"Dataset revision {fmc_data.metadata.configuration_revision}; TX/RX delay {dict(fmc_data.metadata.requested_parameters)['tx_delay_us']:g} / {dict(fmc_data.metadata.requested_parameters)['rx_delay_us']:g} us; source: {fmc_data.metadata.buffer_source}")
            self.update_data_view()
            self._set_busy(False)
            return
        self.ascan_data = None
        self.fmc_data = fmc_data

        bscan_processor = BScanProcessor(
            mode="pulse_echo"
        )

        self.bscan_data = bscan_processor.process(
            self.fmc_data
        )

        self.progress_var.set(
            100.0
        )

        total = (
            fmc_data.tx_count
            * fmc_data.rx_count
        )

        self.progress_text_var.set(
            f"{total} / {total}"
        )

        self.data_shape_var.set(
            str(
                fmc_data.shape
            )
        )

        minimum = int(
            fmc_data.data.min()
        )

        maximum = int(
            fmc_data.data.max()
        )

        lower_clip_count = int(
            (fmc_data.data == np.iinfo(fmc_data.data.dtype).min).sum()
        )

        upper_clip_count = int(
            (fmc_data.data == np.iinfo(fmc_data.data.dtype).max).sum()
        )

        total_samples = int(
            fmc_data.data.size
        )

        clip_count = (
            lower_clip_count
            + upper_clip_count
        )

        clip_percent = (
            clip_count
            / total_samples
            * 100.0
            if total_samples > 0
            else 0.0
        )

        self.data_min_var.set(
            str(minimum)
        )

        self.data_max_var.set(
            str(maximum)
        )

        self.save_button.configure(
            state="normal"
        )

        metadata = getattr(fmc_data, 'metadata', None)
        evidence = getattr(metadata, 'frame_evidence', None)
        summary = f"[OK] FMC acquisition complete; shape {fmc_data.shape}"
        if evidence is not None:
            summary += f"; first frame {evidence.accepted_cycles}/{evidence.expected_cycles}"
            if evidence.post_frame_callback_count:
                summary += f"; shutdown callbacks {evidence.post_frame_callback_count}"
        self.log(summary)
        if evidence is not None:
            if evidence.unexpected_post_frame_callbacks or evidence.malformed_post_frame_callbacks:
                self.log(f"[WARN] Post-frame unexpected callbacks: {evidence.unexpected_post_frame_callbacks}; malformed: {evidence.malformed_post_frame_callbacks}")
            if evidence.chronology_overflow:
                self.log('[WARN] Post-frame chronology overflow; first-frame integrity and total post-frame counts retained')

        if (
            minimum <= np.iinfo(fmc_data.data.dtype).min
            or maximum >= np.iinfo(fmc_data.data.dtype).max
        ):
            self.log(
                "[NOTICE] Data reached "
                "representation amplitude limits."
            )

        self.update_data_view()

        self._set_busy(
            False
        )

    # Data viewer

    def open_fmc(self):
        if self.controller.active or self.state.closing:
            return
        path = filedialog.askopenfilename(title="Open FMC dataset (offline)", filetypes=[("NumPy data", "*.npy")])
        if not path:
            return
        def load(context):
            context.check_cancelled()
            data = FMCData.load(path)
            if data.shape[:2] != (16, 16):
                raise ValueError("Production FMC viewer requires (16,16,N).")
            context.check_cancelled()
            return OperationResult(payload={"fmc_view": data}, status="FMC loaded offline; historical dataset")
        self._loading_fmc_view = True
        self.controller.submit(Operation.LOADING, load)
        self._set_busy(True)

    def _loaded_fmc_view(self, data):
        self.ascan_data = None
        self.fmc_data = data
        self.bscan_data = BScanProcessor(mode="pulse_echo").process(data)
        self.state.dataset_revision = data.metadata.configuration_revision
        self.state.dataset_mode = "FMC"
        self.state.dataset_stale = True
        self.tx_spinbox.configure(to=15)
        self.rx_spinbox.configure(to=15)
        self.workspace.select(self.display_panels['FMC'])
        self.view_mode_var.set('A-Scan')
        self._set_busy(False)
        self.update_data_view()
        self.log('[OK] FMC loaded offline; historical provenance retained; no acquisition')

    def update_data_view(self):
        if hasattr(self, "workspace"):
            name = self.workspace.tab(self.workspace.select(), "text")
            if name not in {"A-scan", "FMC", "B-scan"}:
                return
            self.figure, self.axes, self.canvas = self.plots[name]
            if name == "FMC" and self.ascan_data is not None:
                return
            if name == "FMC" and self.fmc_trace_view_var.get() == "All diagonal traces":
                if self.fmc_data is not None:
                    self._show_fmc_diagonal()
                return
        mode = self.view_mode_var.get()

        if mode == "A-Scan":
            if not hasattr(self, "workspace"):
                self.bscan_controls.grid_remove()
                self.ascan_controls.grid()

            if self.ascan_data is not None:
                self._show_single_ascan()
            elif self.fmc_data is not None:
                self._show_ascan()

        elif mode == "B-Scan":
            if not hasattr(self, "workspace"):
                self.ascan_controls.grid_remove()
                self.bscan_controls.grid()

            if self.bscan_data is not None:
                self._show_bscan()

    def _ascan_summary(self):
        dataset = self.ascan_data
        c = dict(dataset.metadata.requested_parameters)
        t = dataset.metadata.timing
        return (f"TX {c['tx_element']} / RX {c['rx_element']}    Pulse width: {c['pulser_width_us']:g} us    "
                f"Gain: {c['analog_gain_db']:g} / {c['digital_gain_db']:g} dB\n"
                f"Start: {t.start_s * 1e6:g} us    Range: {t.range_s * 1e6:g} us    "
                f"Sampling: {t.sampling_hz / 1e6:g} MHz    Samples: {t.point_count}\n{mapping_summary(dataset.metadata.probe)}")

    def _show_single_ascan(self):
        self.axes.clear()
        self.axes.plot(self.ascan_data.metadata.time_us, self.ascan_data.data, linewidth=1.0)
        c = dict(self.ascan_data.metadata.requested_parameters)
        self.axes.set_title(f"Single-element A-scan - TX {c['tx_element']} / RX {c['rx_element']}" + (" (stale data)" if self.state.dataset_stale else ""))
        self.axes.set_xlabel("Time (us)")
        self.axes.set_ylabel("Signed amplitude")
        self.axes.grid(True, alpha=0.25)
        self.figure.set_layout_engine("tight")
        self.canvas.draw_idle()

    def _show_ascan(self):
        try:
            tx = int(self.tx_view_var.get())
            rx = int(self.rx_view_var.get())
            scan = self.fmc_data.get_ascan(tx, rx)

        except Exception as exc:
            messagebox.showerror(
                "A-Scan Error",
                str(exc),
            )
            return

        self.axes.clear()

        self.axes.plot(
            self.fmc_data.time_us,
            scan,
            linewidth=1.0,
        )
        self.dataset_summary_var.set(dataset_summary(self.fmc_data) + f"\nSelected: TX {tx} / RX {rx}")
        self.inspection_status_var.set("Individual TX/RX - raw signed samples; display processing only")

        self.axes.set_title(
            f"FMC A-scan - TX {tx} / RX {rx}" + (" (stale data)" if self.state.dataset_stale else "")
        )
        metadata = getattr(self.fmc_data, "metadata", None)
        self.axes.set_xlabel("Sample index (metadata incomplete)" if metadata is not None and metadata.time_us is None else "Time (us)")
        self.axes.set_ylabel("Signed amplitude")
        self.axes.grid(True, alpha=0.25)

        self.figure.set_layout_engine("tight")
        self.canvas.draw_idle()

    def _show_fmc_diagonal(self):
        if self.bscan_data is None:
            return
        display = display_traces(self.bscan_data.data, normalization=self.fmc_diagonal_normalization_var.get())
        self.axes.clear()
        for element, trace in enumerate(display.data):
            self.axes.plot(self.fmc_data.time_us, trace, linewidth=.8, color=plt.get_cmap("tab20")(element / max(1, len(display.data))), label=f"TX {element} / RX {element}")
        self.axes.set_title("FMC diagonal traces - logical TX=RX" + (" (stale data)" if self.state.dataset_stale else ""), fontsize=10)
        metadata = getattr(self.fmc_data, "metadata", None)
        self.axes.set_xlabel("Sample index (metadata incomplete)" if metadata is not None and metadata.time_us is None else "Time (us)")
        self.axes.set_ylabel("Signed" if self.fmc_diagonal_normalization_var.get() == "None" else "Scaled signed", fontsize=9)
        self.axes.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=6, ncol=2, frameon=False, labelspacing=.1, columnspacing=.5, handlelength=1)
        self.axes.grid(True, alpha=.25)
        self.dataset_summary_var.set(dataset_summary(self.fmc_data) + "\nAll diagonal TX=RX traces; logical channels only")
        self.inspection_status_var.set(display.description)
        self.figure.set_layout_engine("tight")
        self.canvas.draw_idle()

    def _show_bscan(self):
        if self.bscan_data is None:
            return
        metadata = getattr(self.fmc_data, "metadata", None)
        legacy = metadata is not None and metadata.time_us is None
        time_us = self.bscan_data.time_us
        try:
            if legacy:
                gate_mask = np.ones(self.bscan_data.point_count, dtype=bool)
            else:
                gate_start = float(self.bscan_gate_start_var.get())
                gate_end = float(self.bscan_gate_end_var.get())
                if not math.isfinite(gate_start) or not math.isfinite(gate_end) or gate_end <= gate_start:
                    raise ValueError("Gate must have finite start/end with end greater than start.")
                gate_mask = (time_us >= gate_start) & (time_us <= gate_end)
                if not np.any(gate_mask):
                    raise ValueError("The selected gate contains no samples.")
            display = display_traces(self.bscan_data.data[:, gate_mask], self.bscan_display_var.get(), self.bscan_normalization_var.get(), self.bscan_contrast_var.get())
        except ValueError as exc:
            messagebox.showerror("B-Scan Display Error", str(exc))
            return
        gated_time = time_us[gate_mask]
        # Half-sample edges keep even a single-sample gate visible with correct coordinates.
        step = float(time_us[1] - time_us[0]) if len(time_us) > 1 else 1.0
        extent = [-.5, self.bscan_data.element_count - .5, gated_time[-1] + step / 2, gated_time[0] - step / 2]
        self.axes.clear()
        vmin = -display.limit if self.bscan_display_var.get() == "RF" else 0.0
        self.axes.imshow(display.data.T, aspect="auto", extent=extent, interpolation="nearest", cmap="gray", vmin=vmin, vmax=display.limit)
        title = f"FMC Diagonal Pulse-Echo B-scan {self.bscan_display_var.get()}"
        suffix = " (metadata incomplete; gates unavailable)" if legacy else f" ({gated_time[0]:.2f}-{gated_time[-1]:.2f} us)"
        self.axes.set_title(title + suffix + (" (stale data)" if self.state.dataset_stale else ""), fontsize=9)
        self.axes.set_xlabel("Logical channel")
        self.axes.set_ylabel("Sample index; time gates unavailable" if legacy else "Time (us)")
        self.axes.set_xticks(range(self.bscan_data.element_count))
        self.inspection_status_var.set(display.description + ("; time gates unavailable" if legacy else ""))
        self.figure.set_layout_engine("tight")
        self.canvas.draw_idle()

    # Save

    def save_fmc(self):
        if self.ascan_data is not None:
            path = filedialog.asksaveasfilename(title="Save A-scan data", initialdir=DATA_DIR, initialfile="single_element_ascan.npy",
                                              defaultextension=".npy", filetypes=[("NumPy files", "*.npy")])
            if path:
                try:
                    save_dataset(path, self.ascan_data.data, self.ascan_data.metadata)
                    self.log(f"[OK] A-scan and metadata saved: {path}")
                except Exception as exc:
                    messagebox.showerror("Save Error", str(exc))
            return
        if self.fmc_data is None:
            messagebox.showwarning(
                "No FMC Data",
                "Acquire FMC data first.",
            )
            return

        file_path = (
            filedialog.asksaveasfilename(
                title="Save FMC Data",
                initialdir=DATA_DIR,
                initialfile="fmc16x16.npy",
                defaultextension=".npy",
                filetypes=[
                    (
                        "NumPy files",
                        "*.npy",
                    ),
                    (
                        "All files",
                        "*.*",
                    ),
                ],
            )
        )

        if not file_path:
            return

        try:
            saved_path = (
                self.fmc_data.save(
                    file_path
                )
            )

            self.log(
                f"[OK] FMC saved: "
                f"{saved_path}"
            )

        except Exception as exc:
            messagebox.showerror(
                "Save Error",
                str(exc),
            )

    # State

    def _set_busy(self, busy):
        self.busy = busy or self.controller.active or self.state.closing
        connected = self.state.connection == ConnectionState.CONNECTED
        editable = not self.busy
        for entry in self.config_entries:
            entry.configure(state="normal" if editable else "disabled")
        for selector in getattr(self, "channel_selectors", []):
            selector.configure(state="readonly" if editable else "disabled")
        # Keep the established network endpoint fixed.
        self.ip_entry.configure(state="readonly")
        self.port_entry.configure(state="readonly")
        self.connect_button.configure(state="normal" if editable and self.state.connection == ConnectionState.DISCONNECTED else "disabled")
        self.disconnect_button.configure(state="normal" if editable and self.state.connection != ConnectionState.DISCONNECTED else "disabled")
        self.apply_button.configure(state="normal" if editable and self.state.apply_ready else "disabled")
        self.acquire_button.configure(text={"A-scan": "Acquire A-scan", "FMC": "Acquire FMC", "PA": "Acquire PA"}[self.state.mode])
        self.acquire_button.configure(state="normal" if editable and self.state.acquisition_ready else "disabled")
        self.save_button.configure(state="normal" if editable and (self.fmc_data is not None or self.ascan_data is not None) else "disabled")
        if self.state.closing:
            text = "Closing / waiting for cleanup"
        elif self.state.connection == ConnectionState.ERROR:
            text = "Connection uncertain / error"
        elif self.controller.active:
            text = self.state.operation.value.capitalize()
        else:
            text = self.state.connection.value.capitalize()
        self.connection_status_var.set(f"{text}; config: {self.state.configuration.value}")
        for name in ("mode_selector", "preview_button", "stop_button"):
            if hasattr(self, name):
                enabled = self.controller.active and not self.state.closing if name == "stop_button" else editable
                getattr(self, name).configure(state=("readonly" if name == "mode_selector" else "normal") if enabled else "disabled")
        for entry in getattr(self, "probe_entries", []) + getattr(self, "pa_entries", []):
            entry.configure(state="normal" if editable else "disabled")
        self._refresh_presentation()
        if hasattr(self, "tfm_workspace"):
            self.tfm_workspace.refresh()


    # Controller events

    def _configuration_variables(self):
        return (self.tx_count_var, self.rx_count_var, self.range_var, self.analog_gain_var,
                self.digital_gain_var, self.pulser_width_var, self.filter_var, self.time_slot_var) + tuple(self.ascan_vars.values())

    def _configuration_edited(self, *args):
        try:
            self._read_configuration()
            valid = True
        except (ValueError, tk.TclError):
            valid = False
        self.state.edit_configuration(valid)
        self._mark_stale_data()
        self._set_busy(False)

    def _mark_stale_data(self):
        if self.state.dataset_stale and self.ascan_data is not None:
            self.data_shape_var.set(f"{self.ascan_data.data.shape} (stale)")
            self.update_data_view()
        if self.state.dataset_stale and self.fmc_data is not None:
            self.data_shape_var.set(f"{self.fmc_data.shape} (stale)")
            self.update_data_view()

    def _consume_events(self):
        if self._destroyed:
            return
        for event in self.controller.drain_events():
            try:
                self._handle_controller_event(event)
            except Exception as exc:
                # A display failure must not stop the cleanup/event pump.
                self.state.fail(event.operation, str(exc))
                self._operation_error("UI update failed", exc)
        self._set_busy(False)
        if self.state.shutdown_complete and not self.controller.active:
            self._destroyed = True
            for figure, axes, canvas in getattr(self, "plots", {}).values():
                plt.close(figure)
            plt.close(self.figure)
            self.root.destroy()
            return
        self.root.after(25, self._consume_events)

    def _handle_controller_event(self, event):
        if event.operation == Operation.LOADING and getattr(self, '_loading_fmc_view', False):
            if event.kind == 'completed':
                self._loading_fmc_view = False
                if not self.state.closing:
                    self._loaded_fmc_view(event.payload.payload['fmc_view'])
                return
            if event.kind in {'error', 'cancelled'}:
                self._loading_fmc_view = False
                self._operation_error('FMC load failed', event.payload)
                self._set_busy(False)
                return
            return
        if event.operation == Operation.APPLYING and event.mode == "PA" and event.kind in {"completed", "error", "cancelled"}:
            self.state.configuration_modes = None
        if event.operation in {Operation.LOADING, Operation.RECONSTRUCTING} and hasattr(self, "tfm_workspace"):
            self.tfm_workspace.handle_event(event)
        if event.kind == "progress":
            self._update_progress(*event.payload)
        elif event.kind == "error":
            self._log_readback()
            self._operation_error(f"{event.operation.value.capitalize()} failed", event.payload)
        elif event.kind == "cancelled":
            self.log(f"[CANCELLED] {event.operation.value}; worker stopped")
        elif event.kind == "completed":
            if self.state.closing:
                self.log(f"[OK] {event.operation.value} worker completed")
            elif event.operation == Operation.CONNECTING:
                self._connect_success(event.payload.payload)
            elif event.operation == Operation.APPLYING:
                self._apply_config_success(*event.payload.payload)
            elif event.operation == Operation.ACQUIRING:
                profile = getattr(event.payload.payload, 'timing', None)
                if profile is not None:
                    profile.mark('requested', getattr(self, '_fmc_requested_at', profile.marks['worker_start']))
                    profile.mark('gui_delivered')
                self._acquisition_success(event.payload.payload)
                if profile is not None:
                    profile.mark('gui_update_done')
                    self._finish_fmc_timing(event.payload.payload)
            elif event.operation == Operation.DISCONNECTING:
                self._disconnect_success()

    def _finish_fmc_timing(self, data):
        profile = data.timing
        canvas = self.canvas
        # Worker has completed. GUI and Matplotlib observations belong to the Tk thread.
        def record(event=None):
            if event is not None:
                canvas.mpl_disconnect(connection)
                if self.fmc_data is not data:
                    return
                profile.mark('draw_complete')
            report = profile.report()
            if data.metadata is not None:
                data.metadata = replace(data.metadata, timing_profile=tuple(report.items()))
        record()
        connection = canvas.mpl_connect('draw_event', record)
        canvas.draw_idle()

    def _log_readback(self):
        details = self.state.verification_mismatches
        for mismatch in details[:20]:
            self.log(f"[READBACK MISMATCH] {mismatch[:240]}")
        if len(details) > 20:
            self.log(f"[READBACK] {len(details) - 20} additional diagnostics retained in verification state; output bounded.")
        snapshot = self.state.actual_snapshot
        if snapshot is not None and snapshot.cycles:
            self.log(f"[READBACK] Cycle count: {snapshot.cycle_count}; MultiChannel: supported={snapshot.multichannel_supported} / enabled={snapshot.multichannel_enabled}")
            if snapshot.mode == "FMC" and self.state.configuration_verified:
                tx = sorted({element for cycle in snapshot.cycles for element in (cycle.tx_aperture or ())})
                rx = sorted({element for cycle in snapshot.cycles for element in (cycle.rx_aperture or ())})
                self.log(f"[READBACK] TX logical aperture: {tx}; RX logical aperture: {rx}")
                self.log(f"[OK] FMC configuration {self.state.configuration_label.lower()}; acquisition OFF")
            timing = snapshot.cycles[0]
            start = "unavailable" if timing.start_s is None else f"{timing.start_s * 1e6:.6f} us"
            rate = "unavailable" if timing.sampling_hz is None else f"{timing.sampling_hz / 1e6:.6f} MHz"
            self.log(f"[READBACK] Start {start} | Range {'unavailable' if timing.range_s is None else format(timing.range_s * 1e6, 'g') + ' us'} | Sampling {rate} | Samples {timing.point_count}")

    # Error handling

    def _operation_error(
        self,
        title,
        exception,
    ):
        self.log(
            f"[ERROR] {title}: {str(exception)[:1000]}"
        )

        self._set_busy(
            False
        )

        self.warning_var.set(display_text(f"{title}: {str(exception)[:650]}"))

    # Logging

    def log(
        self,
        message,
    ):
        message = display_text(message)
        self._visible_log_lines = append_visible_log(self.log_text, self.diagnostic_history, message, self._visible_log_lines)

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._visible_log_lines = 0

    # Shutdown

    def on_close(self):
        if self.state.shutdown_complete:
            return
        if self.state.closing and self.controller.active:
            return
        if self.controller.active and not messagebox.askyesno(
            "Exit", "Request cancellation and close after the worker finishes cleanup?"
        ):
            return
        self.log("Closing; waiting for the owning worker and device cleanup...")
        self.controller.request_shutdown(self.backend.close)
        self._set_busy(True)


def run_gui():
    root = tk.Tk()

    OEMPAGUI(
        root
    )

    root.mainloop()


if __name__ == "__main__":
    run_gui()
