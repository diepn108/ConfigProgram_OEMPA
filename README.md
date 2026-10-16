# OEM-PA Configuration and Imaging Program

Windows x64 Tk/Matplotlib application for AOS OEM-PA 16:16. Acquisition modes are A-scan, FMC and Phased Array; PA acquisition remains safety-gated. FMC uses the verified 256-cycle MultiHWChannel table, **not dedicated FMC**. B-scan and experimental homogeneous-medium TFM process existing data offline.

Read [AGENTS.md](AGENTS.md) for verified behavior, restrictions and checkpoints. Hardware operations require a deliberate user action and an appropriately configured system. No automatic connection/acquisition occurs at startup. Never change network settings as an installation shortcut.

## Install on another computer

1. Clone this repository into any writable directory. No particular Windows username or checkout location is required.
2. Install **64-bit Python 3.14 with Tcl/Tk** and Microsoft Visual Studio 2022 C++ Build Tools (x64 toolchain/Windows SDK).
3. Obtain/install the licensed **AOS OEMPA 1.1.5.4 SDK/runtime** separately, including its Common/UserHeaders and UTKernel x64 libraries. Vendor binaries, headers, manuals and libraries are not supplied through Git. Their redistribution requires AOS authorization; no license grant is implied here.
4. From the checkout in PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tkinter
cmd /c bridge\build_bridge.cmd
.\.venv\Scripts\python.exe main.py
```

Close any existing OEM-PA GUI before rebuilding its DLL. The build does not connect to a device. The generated `bridge/oempa_bridge.dll` must stay beside the bridge sources or be deployed there. Keep the required Microsoft x64 VC runtime installed. The pinned Python packages are the versions tested for this checkpoint; they do not install AOS or a Windows driver.

### Optional paths

Defaults use the normal Windows installation directories, not a personal profile:

| Environment variable | Default / meaning |
|---|---|
| `OEMPA_AOS_RUNTIME` | `%ProgramFiles%\AOS\OEMPA 1.1.5.4`; runtime DLL directory |
| `OEMPA_AOS_SOURCES` | `%ProgramData%\AOS\OEMPA 1.1.5.4\Sources`; build headers/libraries |
| `OEMPA_VCVARS` | Standard VS2022 BuildTools `vcvars64.bat`; override for another VS installation, or use an initialized x64 Developer Command Prompt |
| `OEMPA_BRIDGE_OUTPUT` | `oempa_bridge.dll`; alternate build filename only, not a runtime selection |

For example, set `$env:OEMPA_AOS_RUNTIME = 'D:\AOS\OEMPA 1.1.5.4'` before launch if AOS was installed there. Do not copy unrelated DLL versions into the checkout. Historical diagnostic scripts now resolve the project from their own location; they still require explicit hardware authorization and must not be run indiscriminately.

The OEM-PA endpoint remains `192.168.1.11:5001`. The PC adapter/device/firewall must already be configured by the responsible operator. Installing this application does not configure them.

## Offline tests and GUI validation

**Do not run unrestricted pytest/unittest discovery:** numerous historical `test_*.py` scripts can connect/write/acquire. The inspected offline suite is:

```powershell
cmd /c tests\build_fmc_batch_readback_test.cmd
cmd /c tests\build_callback_order_test.cmd
cmd /c tests\build_fmc_first_frame_test.cmd
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_ui_*.py' -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_tfm_offline.py' -q
.\.venv\Scripts\python.exe tools\validate_gui_usability_offline.py
.\.venv\Scripts\python.exe tools\validate_tfm_production_offline.py --output artifacts\tfm_review
.\.venv\Scripts\python.exe tools\repository_audit.py
```

The three native test executables have **no AOS SDK linkage**. GUI validation installs a fake backend before GUI import, forbids device operations, uses synthetic data, and checks both supported window sizes. Run real Tk in a desktop session; do not add machine-specific Tcl paths to the application to work around a restricted execution sandbox.

## Source distribution and local files

```text
AGENTS.md, README.md, requirements.txt, .gitignore
main.py, gui.py
bridge/       C++ source/headers, SDK build recipe
oempa/        device adapter, configuration, acquisition, provenance, imaging
ui/           state/controller and Tk views
configs/      verified/reference configurations (including fmc16_full.txt and backup_original.txt)
scripts/      configurable x64 compiler setup
tests/        offline tests/native harnesses and explicitly hardware-capable diagnostics
tools/        offline validation/audit and opt-in hardware diagnostics
docs/         timing, vendor-source conclusions and cleanup manifest
data/README.md
```

Local `artifacts/`, acquired `data/`, vendor `dll/` copies, Python caches, native outputs and generated GUI/debug configurations are ignored. Historical hardware evidence, real experiment arrays/sidecars and useful reference configurations are preserved locally, not automatically published or deleted. In particular, the real 18-mm dataset and every original dataset/configuration are retained. Transfer an approved dataset manually **with its `.npy.json` sidecar** when needed; offline tests use synthetic fixtures and do not require lab data.

There was no `.git` directory at the cleanup checkpoint, so no claim is made about an existing Git index/history. The audit scans source-distribution candidates for personal paths and selected secret formats without printing matching secrets. Review `git status` and the staged diff before your own initial commit/push. AGENTS deliberately retains device/network observations; review those for your intended audience. The project has no newly assigned public source license; choose permissions appropriately before public redistribution. No push is performed by tooling.

See [FMC timing and manual benchmark](docs/fmc_timing.md) and [cleanup inventory](docs/repository_cleanup.md).
