"""Engineering display tabs; no device access."""

from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from ui.setup_panel import entry_row
from ui.tfm_workspace import TFMWorkspace
from ui.fmc_inspection import NORMALIZATIONS, CONTRASTS


def build_workspace(app, parent):
    app.workspace = ttk.Notebook(parent)
    app.workspace.pack(fill="both", expand=True)
    app.display_panels = {}
    app.plots = {}
    for name in ("A-scan", "FMC", "B-scan", "Phased Array", "TFM"):
        panel = ttk.Frame(app.workspace, padding=8)
        app.workspace.add(panel, text=name)
        app.display_panels[name] = panel
        if name == "TFM":
            app.tfm_workspace = TFMWorkspace(app, panel)
        figure = plt.Figure(figsize=(7, 4), dpi=100, layout="compressed" if name == "TFM" else "tight")
        axes = figure.add_subplot(111)
        canvas = FigureCanvasTkAgg(figure, master=app.tfm_workspace.image_panel if name == "TFM" else panel)
        app.plots[name] = (figure, axes, canvas)
    app.workspace.bind("<<NotebookTabChanged>>", app.change_display)
    for name in ("A-scan", "FMC", "B-scan"):
        panel = app.display_panels[name]
        if name == "B-scan":
            ttk.Label(panel, text="Source: current FMC cube; captured timing/provenance in FMC tab").pack(anchor="w")
        else:
            ttk.Label(panel, textvariable=app.dataset_summary_var, wraplength=850).pack(anchor="w")
        ttk.Label(panel, textvariable=app.stale_var).pack(anchor="w")
    app.ascan_controls = ttk.Frame(app.display_panels["FMC"])
    app.ascan_controls.pack(fill="x", pady=6)
    for column, (label, variable, attr) in enumerate((("TX", app.tx_view_var, "tx_spinbox"), ("RX", app.rx_view_var, "rx_spinbox"))):
        ttk.Label(app.ascan_controls, text=label).pack(side="left", padx=6)
        control = ttk.Spinbox(app.ascan_controls, from_=0, to=15, textvariable=variable, width=5, command=app.update_data_view)
        control.pack(side="left")
        control.bind("<Return>", lambda event: app.update_data_view())
        control.bind("<FocusOut>", lambda event: app.update_data_view())
        setattr(app, attr, control)
    ttk.Button(app.ascan_controls, text="Save cube", command=app.save_fmc).pack(side="left", padx=10)
    ttk.Button(app.ascan_controls, text="Open FMC (offline)", command=app.open_fmc).pack(side="left", padx=6)
    inspection = ttk.Frame(app.display_panels["FMC"])
    inspection.pack(fill="x", pady=(0, 4))
    for label, variable, values, width in (("Trace view", app.fmc_trace_view_var, ("Individual TX/RX", "All diagonal traces"), 19),
                                            ("Diagonal scale", app.fmc_diagonal_normalization_var, NORMALIZATIONS, 10)):
        ttk.Label(inspection, text=label).pack(side="left", padx=(0, 4))
        control = ttk.Combobox(inspection, textvariable=variable, values=values, state="readonly", width=width)
        control.pack(side="left", padx=(0, 8))
        control.bind("<<ComboboxSelected>>", lambda event: app.update_data_view())
    ttk.Label(app.display_panels["FMC"], textvariable=app.inspection_status_var, wraplength=650).pack(anchor="w")
    bscan = app.display_panels["B-scan"]
    ttk.Label(bscan, text="FMC diagonal pulse-echo - not mechanically scanned; RF shows callback MAX.", wraplength=650).pack(anchor="w", pady=(4, 0))
    app.bscan_controls = ttk.Frame(bscan)
    app.bscan_controls.pack(fill="x", pady=6)
    display = ttk.Combobox(app.bscan_controls, textvariable=app.bscan_display_var, values=("RF", "Absolute"), state="readonly", width=10)
    display.pack(side="left")
    display.bind("<<ComboboxSelected>>", lambda event: app.update_data_view())
    for label, variable in (("Gate start (us)", app.bscan_gate_start_var), ("End (us)", app.bscan_gate_end_var)):
        ttk.Label(app.bscan_controls, text=label).pack(side="left", padx=5)
        ttk.Entry(app.bscan_controls, textvariable=variable, width=8).pack(side="left")
    ttk.Button(app.bscan_controls, text="Update gate", command=app.update_data_view).pack(side="left", padx=6)
    processing = ttk.Frame(bscan)
    processing.pack(fill="x", pady=(0, 4))
    for label, variable, values, width in (("Normalize", app.bscan_normalization_var, NORMALIZATIONS, 10),
                                           ("Contrast", app.bscan_contrast_var, CONTRASTS, 19)):
        ttk.Label(processing, text=label).pack(side="left", padx=(0, 4))
        control = ttk.Combobox(processing, textvariable=variable, values=values, state="readonly", width=width)
        control.pack(side="left", padx=(0, 8))
        control.bind("<<ComboboxSelected>>", lambda event: app.update_data_view())
    ttk.Label(bscan, text="Per trace removes channel amplitude ratios; scaling uses displayed samples.", wraplength=650).pack(anchor="w")
    ttk.Label(bscan, textvariable=app.inspection_status_var, wraplength=650).pack(anchor="w")
    pa = app.display_panels["Phased Array"]
    ttk.Label(pa, text="OFFLINE PREVIEW ONLY - physical steering/channel mapping unverified").pack(anchor="w")
    ttk.Label(pa, text="PA receive zero-tail findings remain unresolved. Linear/sector scan pending.").pack(anchor="w")
    ttk.Label(pa, textvariable=app.pa_summary_var, wraplength=600).pack(anchor="w")
    for name, (figure, axes, canvas) in app.plots.items():
        plot_parent = app.tfm_workspace.image_panel if name == "TFM" else app.display_panels[name]
        NavigationToolbar2Tk(canvas, plot_parent, pack_toolbar=False).pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(fill="both", expand=True)
        axes.set_title("No dataset" if name != "Phased Array" else "No calculated focal law")
    app.figure, app.axes, app.canvas = app.plots["A-scan"]
