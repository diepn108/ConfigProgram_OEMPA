"""Setup widgets: drafts and observed hardware remain separate."""

import tkinter as tk
from tkinter import ttk


def entry_row(parent, row, label, variable, pady=4):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=pady)
    entry = ttk.Entry(parent, textvariable=variable, width=18)
    entry.grid(row=row, column=1, sticky="ew", pady=pady)
    return entry


def build_setup(app, parent):
    notebook = ttk.Notebook(parent)
    notebook.pack(fill="both", expand=True)
    app.setup_notebook = notebook
    panels = {}
    for name in ("Device", "Probe", "Acquisition", "Mode Settings"):
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text=name)
        panels[name] = frame
    device = panels["Device"]
    app.ip_entry = entry_row(device, 0, "OEM-PA IP (fixed)", app.ip_var)
    app.port_entry = entry_row(device, 1, "Port (fixed)", app.port_var)
    app.connect_button = ttk.Button(device, text="Connect", command=app.connect_device)
    app.connect_button.grid(row=2, column=0, pady=8)
    app.disconnect_button = ttk.Button(device, text="Disconnect", command=app.disconnect_device)
    app.disconnect_button.grid(row=2, column=1, pady=8)
    ttk.Label(device, textvariable=app.connection_status_var, wraplength=310).grid(row=3, column=0, columnspan=2, sticky="w")
    ttk.Label(device, text="Observed cycles:").grid(row=4, column=0, sticky="w")
    ttk.Label(device, textvariable=app.cycle_status_var).grid(row=4, column=1)
    ttk.Label(device, text="MultiHWChannel:").grid(row=5, column=0, sticky="w")
    ttk.Label(device, textvariable=app.multichannel_status_var).grid(row=5, column=1)
    ttk.Label(device, text="Identity / firmware: unavailable in this UI\nLast observed readback; not physical probe identity", wraplength=310).grid(row=6, column=0, columnspan=2, sticky="w", pady=12)
    probe = panels["Probe"]
    ttk.Label(probe, text="Manual description from user-supplied probe label; not device detected.", wraplength=290).grid(row=0, column=0, columnspan=2, sticky="w")
    app.probe_entries = []
    fields = (("brand", "Manufacturer / Brand"), ("model", "Model / Label"), ("frequency", "Nominal frequency (MHz)"),
              ("elements", "Probe element count"), ("pitch", "Pitch (mm)"), ("numbering", "Element numbering"),
              ("marking", "Additional marking"))
    for row, (key, label) in enumerate(fields, 1):
        app.probe_entries.append(entry_row(probe, row, label, app.probe_vars[key], pady=2))
    ttk.Label(probe, text="Complete label").grid(row=8, column=0, columnspan=2, sticky="w")
    complete_label = ttk.Entry(probe, textvariable=app.probe_vars["full_marking"], width=35)
    complete_label.grid(row=9, column=0, columnspan=2, sticky="ew", pady=4)
    app.probe_entries.append(complete_label)
    ttk.Label(probe, text="F5 / 5 MHz: label-derived, inferred.\nAOS-defined logical 0-15 -> elements 1-16\nSource: AOS SDK documentation\nPhysical wiring: Not independently tested\n32 label elements; 16 usable.\nAt label pitch 0.6 mm: span 9.0 mm.", wraplength=310, justify="left").grid(row=10, column=0, columnspan=2, sticky="w", pady=8)
    acquisition_host = panels["Acquisition"]
    acquisition_host.rowconfigure(0, weight=1)
    acquisition_host.columnconfigure(0, weight=1)
    canvas = tk.Canvas(acquisition_host, highlightthickness=0, width=310)
    canvas.grid(row=0, column=0, columnspan=2, sticky="nsew")
    scrollbar = ttk.Scrollbar(acquisition_host, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=2, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    acquisition = ttk.Frame(canvas)
    acquisition.columnconfigure(1, weight=1)
    window_id = canvas.create_window((0, 0), window=acquisition, anchor="nw")
    acquisition.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
    app.acquisition_form = acquisition
    app.acquisition_scroll_canvas = canvas

    app.config_entries = []
    def group(row, title):
        frame = ttk.LabelFrame(acquisition, text=title, padding=6)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        frame.columnconfigure(1, weight=1)
        return frame
    ttk.Label(acquisition, text="Requested / editable").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    pulser = group(1, "Pulser")
    app.config_entries.append(entry_row(pulser, 0, "Pulse Width (us)", app.pulser_width_var))
    receiver = group(2, "Receiver")
    for row, (label, variable) in enumerate((("Analog Gain (dB)", app.analog_gain_var), ("Digital Gain (dB)", app.digital_gain_var), ("Filter", app.filter_var))):
        app.config_entries.append(entry_row(receiver, row, label, variable))
    window = group(3, "Acquisition Window")
    app.start_entry = entry_row(window, 0, "Start (us)", app.ascan_vars["start"])
    app.start_fixed = ttk.Label(window, text="Configuration-defined (FMC / PA)")
    app.start_fixed.grid(row=0, column=1, sticky="w")
    app.start_entry.grid_remove()
    app.config_entries.append(app.start_entry)
    app.config_entries.append(entry_row(window, 1, "Range (us)", app.range_var))
    advanced = group(4, "Advanced")
    app.config_entries.append(entry_row(advanced, 0, "TimeSlot (us)", app.time_slot_var))
    readback = group(5, "Hardware Readback")
    ttk.Label(readback, text="Actual / readback (last observation)").grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(readback, textvariable=app.readback_var, wraplength=290, justify="left").grid(row=1, column=0, columnspan=2, sticky="w")
    mode = panels["Mode Settings"]
    mode_group = ttk.LabelFrame(mode, text="Acquisition Mode", padding=8)
    mode_group.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    mode_group.columnconfigure(1, weight=1)
    ttk.Label(mode_group, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 12))
    app.mode_selector = ttk.Combobox(mode_group, textvariable=app.mode_var, values=("A-scan", "FMC", "Phased Array"), state="readonly", width=18)
    app.mode_selector.grid(row=0, column=1, sticky="ew")
    app.fmc_settings = ttk.LabelFrame(mode, text="FMC Aperture / Cycle Mapping", padding=8)
    app.fmc_settings.grid(row=1, column=0, columnspan=2, sticky="ew")
    ttk.Label(app.fmc_settings, text="TX logical channels: 0-15 (16)\nRX logical channels: 0-15 (16)\nTX/RX combinations: 256\ncycle = TX * 16 + RX\nMultiHWChannel acquisition / replay", justify="left", wraplength=290).grid(row=0, column=0, columnspan=2, sticky="w")
    app.mode_help_label = ttk.Label(mode, textvariable=app.mode_help_var, wraplength=290)
    app.mode_help_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=10)

    app.ascan_settings = ttk.Frame(mode)
    app.ascan_settings.grid(row=1, column=0, columnspan=2, sticky="ew")
    app.ascan_settings.columnconfigure(0, weight=1)
    channels = ttk.LabelFrame(app.ascan_settings, text="Channels", padding=8)
    channels.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    channels.columnconfigure(1, weight=1)
    app.channel_selectors = []
    for row, (key, label) in enumerate((("tx", "Transmit (TX)"), ("rx", "Receive (RX)"))):
        ttk.Label(channels, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
        control = ttk.Combobox(channels, textvariable=app.ascan_vars[key], values=tuple(str(i) for i in range(16)), state="readonly", width=10)
        control.grid(row=row, column=1, sticky="ew", pady=4)
        app.channel_selectors.append(control)
        app.config_entries.append(control)
    ttk.Label(channels, text="Logical OEM-PA channels 0-15\nAOS-defined probe elements 1-16\nPhysical wiring: Not independently tested", wraplength=280).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
    timing = ttk.LabelFrame(app.ascan_settings, text="Advanced", padding=8)
    timing.grid(row=1, column=0, sticky="ew")
    timing.columnconfigure(1, weight=1)
    for row, (key, label) in enumerate((("tx_delay", "TX Delay"), ("rx_delay", "RX Delay"))):
        entry = entry_row(timing, row, label, app.ascan_vars[key])
        entry.configure(width=10)
        ttk.Label(timing, text="us").grid(row=row, column=2, sticky="w", padx=(6, 0))
        app.config_entries.append(entry)
    app.ascan_settings.grid_remove()
    ttk.Label(app.fmc_settings, text="Probe Mapping\nLogical 0-15 -> Elements 1-16\nSource: AOS SDK documentation\nPhysical wiring: Not independently tested", justify="left", wraplength=290).grid(row=1, column=0, columnspan=2, sticky="w", pady=8)
    app.fmc_expected_var = tk.StringVar(value="Expected Dataset\nRaw: 256 x N\nFMC: 16 x 16 x N\nN: pending current verified readback")
    ttk.Label(app.fmc_settings, textvariable=app.fmc_expected_var, justify="left", wraplength=290).grid(row=2, column=0, columnspan=2, sticky="w", pady=8)
    app.pa_settings = ttk.LabelFrame(mode, text="PA geometry / aperture (offline preview)", padding=8)
    app.pa_settings.grid(row=1, column=0, columnspan=2, sticky="ew")
    app.pa_entries = []
    for row, (key, label) in enumerate((("start", "Logical aperture start"), ("count", "Aperture count"), ("angle", "Steering angle (deg)"), ("pitch", "Assumed pitch (mm)"), ("velocity", "Velocity (m/s)"))):
        app.pa_entries.append(entry_row(app.pa_settings, row, label, app.pa_vars[key]))
    app.preview_button = ttk.Button(app.pa_settings, text="Calculate offline law", command=app.preview_pa)
    app.preview_button.grid(row=5, column=0, columnspan=2, pady=6)
    ttk.Label(app.pa_settings, text="Physical mapping / steering direction unverified", wraplength=290).grid(row=6, column=0, columnspan=2, sticky="w")
    app.pa_settings.grid_remove()
