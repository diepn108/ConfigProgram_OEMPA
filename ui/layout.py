"""Application composition for setup, workspace and persistent actions."""

import tkinter as tk
from tkinter import ttk

from ui.setup_panel import build_setup
from ui.workspace import build_workspace


def build_layout(app):
    app.root.columnconfigure(0, weight=1)
    app.root.rowconfigure(0, weight=1)
    main = ttk.Frame(app.root, padding=10)
    main.grid(row=0, column=0, sticky="nsew")
    main.columnconfigure(0, weight=1)
    main.rowconfigure(2, weight=1)
    ttk.Label(main, text="OEM-PA Configuration & Acquisition", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(main, textvariable=app.header_var).grid(row=1, column=0, sticky="w", pady=8)
    app.vertical_panes = ttk.Panedwindow(main, orient="vertical")
    app.vertical_panes.grid(row=2, column=0, sticky="nsew")
    upper = ttk.Frame(app.vertical_panes)
    upper.columnconfigure(0, weight=1)
    upper.rowconfigure(0, weight=1)
    app.vertical_panes.add(upper, weight=3)
    panes = ttk.Panedwindow(upper, orient="horizontal")
    panes.grid(row=0, column=0, sticky="nsew")
    setup = ttk.Frame(panes, width=360)
    workspace = ttk.Frame(panes)
    panes.add(setup, weight=0)
    panes.add(workspace, weight=1)
    build_setup(app, setup)
    build_workspace(app, workspace)
    actions = ttk.Frame(upper, padding=(0, 8))
    actions.grid(row=1, column=0, sticky="ew")
    for attr, text, command in (("apply_button", "Apply Configuration", app.apply_configuration), ("acquire_button", "Acquire FMC", app.acquire_fmc), ("stop_button", "Stop", app.stop_operation), ("save_button", "Save data", app.save_fmc)):
        button = ttk.Button(actions, text=text, command=command)
        button.pack(side="left", padx=(0, 6))
        setattr(app, attr, button)
    ttk.Progressbar(actions, variable=app.progress_var, maximum=100, length=170).pack(side="left", padx=8)
    ttk.Label(actions, textvariable=app.progress_text_var).pack(side="left")
    ttk.Label(upper, textvariable=app.warning_var, wraplength=1150, justify="left").grid(row=2, column=0, sticky="w")
    log = ttk.LabelFrame(app.vertical_panes, text="Status / Errors / Readback", padding=6)
    log.columnconfigure(0, weight=1)
    log.rowconfigure(1, weight=1)
    app.vertical_panes.add(log, weight=1)
    ttk.Button(log, text="Clear Log", command=app.clear_log).grid(row=0, column=0, sticky="e", pady=(0, 4))
    app.log_text = tk.Text(log, height=10, wrap="word", state="disabled")
    app.log_text.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(log, orient="vertical", command=app.log_text.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    app.log_text.configure(yscrollcommand=scroll.set)
    def initial_divider():
        if hasattr(app.vertical_panes, "winfo_height"):
            height = app.vertical_panes.winfo_height()
            if height > 100:
                app.vertical_panes.sashpos(0, int(height * .74))
            else:
                app.root.after(50, initial_divider)
    app.root.after(100, initial_divider)
