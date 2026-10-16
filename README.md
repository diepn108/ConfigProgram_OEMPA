# OEM-PA Configuration and Imaging Program

ConfigProgram_OEMPA is a Windows program for controlling and acquiring ultrasonic data from an AOS OEM-PA 16:16 phased-array system.

The program provides a graphical user interface (GUI) for:

- A-scan acquisition
- Full Matrix Capture (FMC)
- B-scan visualization
- Experimental Total Focusing Method (TFM) imaging
- Phased Array (PA) configuration and acquisition

The program has been developed and tested with an AOS OEM-PA 16:16 system using AOS OEMPA software version 1.1.5.4.

> **Important:** The AOS OEMPA SDK/runtime is not included in this GitHub repository. It must be installed separately.

## 1. What You Need

This program is intended for a 64-bit Windows computer.

The tested development environment uses:

- Windows 64-bit
- Python 3.14.x, 64-bit
- AOS OEMPA SDK/runtime 1.1.5.4, 64-bit
- Microsoft Visual Studio 2022 C++ Build Tools
- Git
- A dedicated Ethernet connection to the OEM-PA

The Python packages used by the program are listed in `requirements.txt`.

## 2. Download the Program

Open PowerShell and choose where you want to store the program.

Run:

```powershell
git clone https://github.com/diepn108/ConfigProgram_OEMPA.git
cd ConfigProgram_OEMPA
```

## 3. Install Python

Install 64-bit Python 3.14 with Tcl/Tk support.

Check the installation with:

```powershell
py -3.14 --version
```

You should see Python 3.14.x.

Create a virtual environment:

```powershell
py -3.14 -m venv .venv
```

Install the required Python packages:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Check that Tkinter is working:

```powershell
.\.venv\Scripts\python.exe -m tkinter
```

A small Tk window should appear. Close it after confirming that it works.

## 4. Install the AOS OEMPA Software

The program depends on the official AOS OEMPA SDK/runtime.

The system used during development was tested with:

```text
AOS OEMPA Kit 64-bit
Version 1.1.5.4
```

The AOS software must be obtained separately from AOS/UTEX or your equipment administrator.

AOS vendor DLLs, libraries, headers, and manuals are not distributed through this repository.

With a standard installation, the program expects the AOS files under locations similar to:

```text
C:\Program Files\AOS\OEMPA 1.1.5.4
C:\ProgramData\AOS\OEMPA 1.1.5.4
```

If AOS is installed somewhere else, see the "Custom Installation Paths" section below.

## 5. Install Microsoft C++ Build Tools

The program communicates with the AOS software through a native C++ bridge.

Install Microsoft Visual Studio 2022 C++ Build Tools with the 64-bit C++ compiler and Windows SDK.

After the AOS software and C++ build tools are installed, build the bridge from the project directory:

```powershell
cmd /c bridge\build_bridge.cmd
```

A successful build creates:

```text
bridge\oempa_bridge.dll
```

Do not move this DLL away from the `bridge` directory.

If the OEM-PA program is already running, close it before rebuilding the DLL.

## 6. Connect the OEM-PA

Connect the computer to the OEM-PA using a dedicated Ethernet adapter.

The configuration tested with this OEM-PA system is:

```text
Computer Ethernet adapter:
IP address:     192.168.1.10
Subnet mask:    255.255.255.0
Default gateway: blank
DNS:             blank

OEM-PA:
IP address:     192.168.1.11
Port:           5001
```

These values describe the system used during development. Confirm the correct network configuration for your own OEM-PA before changing network settings.

Do not change an unrelated university, company, or Internet Ethernet adapter. Configure only the adapter dedicated to the OEM-PA.

### Test the connection

In PowerShell, run:

```powershell
ping 192.168.1.11
```

Then:

```powershell
Test-NetConnection 192.168.1.11 -Port 5001
```

A working TCP connection should report:

```text
TcpTestSucceeded : True
```

If this test fails, fix the Ethernet/OEM-PA connection before trying to acquire ultrasound data.

## 7. Start the Program

From the project directory, run:

```powershell
.\.venv\Scripts\python.exe main.py
```

The GUI should open.

Starting the application does not automatically connect to the OEM-PA or start an acquisition.

## 8. First Hardware Test

For a new installation, test the system in this order:

1. Connect the OEM-PA and probe.
2. Confirm that `192.168.1.11:5001` is reachable.
3. Start the program.
4. Connect to the OEM-PA from the GUI.
5. Start with **A-scan** mode.
6. Select the desired transmit (TX) and receive (RX) elements.
7. Enter the acquisition settings.
8. Click **Apply Configuration**.
9. Confirm that the configuration is verified.
10. Acquire an A-scan and confirm that a waveform is received.
11. After A-scan operation is confirmed, proceed to FMC if needed.

Do not begin with Phased Array acquisition on a new installation.

## 9. What the Different Modes Mean

### A-scan

An A-scan is a single ultrasonic waveform.

The program transmits using a selected element and records the signal from a selected receive element.

A-scan is the recommended mode for checking that a new hardware installation is working.

### FMC

FMC stands for **Full Matrix Capture**.

For the 16-channel OEM-PA configuration, the program acquires every transmit/receive combination:

```text
16 transmit elements × 16 receive elements = 256 A-scans
```

The resulting dataset has the form:

```text
16 × 16 × number of time samples
```

The current implementation uses the verified AOS MultiHWChannel configuration. It does not use the dedicated AOS FMC function.

### B-scan

The B-scan view is created from an existing FMC dataset.

It does not perform another hardware acquisition.

The current B-scan uses the diagonal FMC signals:

```text
TX0/RX0
TX1/RX1
...
TX15/RX15
```

### TFM

TFM stands for **Total Focusing Method**.

TFM uses the full FMC dataset to reconstruct an image of ultrasonic response versus position and depth.

The current TFM implementation assumes a homogeneous material with one sound velocity.

TFM is currently experimental. A bright region in the reconstructed image should not automatically be interpreted as a defect without physical validation.

### Phased Array

Phased Array mode uses multiple transmitting elements with controlled delays to form a beam.

The PA software/configuration infrastructure is implemented, but PA operation is more safety-sensitive and has not been physically validated to the same extent as A-scan and FMC.

Use PA only after the system and experimental setup have been verified.

## 10. Saving Data

FMC data can be saved for later processing.

Experimental measurement files are intentionally not stored in this GitHub repository.

The local `data/` directory can contain acquired datasets, but Git ignores these files by default.

When transferring a saved dataset, also transfer its associated metadata sidecar file when one is present.

## 11. Custom Installation Paths

Normally the program uses the standard AOS installation locations.

If AOS is installed somewhere else, the following environment variables can be used:

| Environment variable | Purpose |
|---|---|
| `OEMPA_AOS_RUNTIME` | Location of the AOS runtime |
| `OEMPA_AOS_SOURCES` | Location of the AOS source headers/libraries |
| `OEMPA_VCVARS` | Location of the Visual Studio x64 `vcvars64.bat` |
| `OEMPA_BRIDGE_OUTPUT` | Alternate bridge build filename |

For example:

```powershell
$env:OEMPA_AOS_RUNTIME = 'D:\AOS\OEMPA 1.1.5.4'
```

Most users with a standard AOS installation should not need to change these variables.

## 12. Repository Structure

```text
ConfigProgram_OEMPA/
│
├── main.py             Program entry point
├── gui.py              GUI integration
├── requirements.txt    Python dependencies
├── README.md           Installation and user guide
├── AGENTS.md           Detailed engineering notes and safety checkpoints
│
├── bridge/             Native C++ bridge source and build script
├── configs/            Reference OEM-PA configurations
├── oempa/              OEM-PA control, acquisition, and imaging code
├── ui/                 GUI components
├── tests/              Tests and diagnostic scripts
├── tools/              Validation and diagnostic utilities
├── docs/               Development and technical documentation
└── data/               Local measurement-data location
```

## 13. Important Safety Notes

- Hardware acquisition occurs only after deliberate user actions.
- Do not access the OEM-PA from acquisition callbacks.
- Do not use the AOS dedicated FMC function with this implementation.
- Do not modify network settings simply to work around a connection problem.
- Do not run unfamiliar hardware diagnostic scripts while the OEM-PA is connected.
- Some scripts under `tests/` and `tools/` are hardware-capable.
- Do not run unrestricted test discovery against connected hardware.
- Start a new hardware installation with A-scan before FMC or Phased Array.
- Do not interpret experimental B-scan or TFM features as physical defects without validation.

## 14. Offline Developer Tests

The following tests are intended for offline validation:

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

Do not run unrestricted `pytest` or `unittest` discovery because some historical diagnostic scripts can communicate with real hardware.

## 15. Additional Documentation

More detailed development information is available in:

- `AGENTS.md` — development history, verified hardware behavior, safety restrictions, and checkpoints
- `docs/fmc_timing.md` — FMC timing and performance information
- `docs/repository_cleanup.md` — repository cleanup information

These files are mainly intended for development and troubleshooting. A normal user should begin with this README.

## License and Vendor Software

The AOS OEMPA SDK/runtime is proprietary vendor software and is not distributed with this repository.

This repository does not grant permission to redistribute AOS software, documentation, libraries, or binaries.

A public open-source license has not yet been assigned to this repository.