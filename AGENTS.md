# ConfigProgram_OEMPA — Codex Project Context

## Purpose
This repository is a standalone configuration, acquisition, and imaging program for an Advanced OEM Solutions (AOS) OEM-PA 16/16 ultrasonic phased-array unit.

It is intentionally separate from the existing MicroPulse 5 Config Program because both systems may be used simultaneously.

The immediate goal is to make the OEM-PA backend reliable first, then integrate the verified capabilities into the GUI. Do not redesign working parts of the project unless necessary.

## Working style
Before editing anything:
1. Read this file completely.
2. Inspect the current repository and current implementation. The repository files are the source of truth for code state.
3. Inspect relevant AOS headers/source/documentation before guessing an SDK behavior or signature.
4. Make the smallest change necessary.
5. Build/run the relevant diagnostic or test after the change.
6. Report exactly what changed, what command was run, and the result.

Use the `Current Development State` section as the active procedure/checkpoint. Update it after every successful diagnostic or major discovery before moving to the next step.

For code style:
- Use clean section comments such as `# Logging` or `// Acquisition`.
- Do not use decorative separator banners such as `# =====` or `# -----`.
- Keep equations/calculations on one line whenever reasonably readable instead of splitting an unfinished expression across lines.
- Avoid unnecessary rewrites of already-working modules.
- Preserve existing public interfaces unless there is a concrete reason to change them.

## Project location and structure
Expected Windows root:

`<repository>`

Important structure:

```text
ConfigProgram_OEMPA/
├── main.py
├── gui.py
├── bridge/
│   ├── oempa_bridge.cpp
│   ├── oempa_bridge.h
│   └── oempa_bridge.dll
├── oempa/
│   ├── __init__.py
│   ├── api.py
│   ├── driver.py
│   ├── config.py
│   ├── acquisition.py
│   ├── fmc.py
│   ├── bscan.py
│   ├── cscan.py
│   ├── scan_grid.py
│   ├── scan_session.py
│   ├── focal_law.py
│   └── pa_config.py
├── configs/
│   ├── backup_original.txt
│   ├── fmc16_tx0.txt
│   ├── fmc16_full.txt
│   ├── pa_test_0deg.txt
│   └── pa_test_30deg.txt
├── data/
│   ├── fmc16x16.npy
│   └── pa_0deg_ascan.npy
└── tests/
    └── multiple backend, FMC, PA, and diagnostic tests
```

Inspect the actual repository because additional tests/files may now exist.

## Hardware/network — do not change
OEM-PA:
- IP: `192.168.1.11`
- TCP port: `5001`
- Device type: OEMPA 16:16
- Firmware ID previously read: `0x2354`
- Serial previously read: `1616F0171228`
- Embedded version: `1.1.5.4`
- Ethernet speed: 1000 Mbps
- MaxCycles: 2047
- PulserPowerMax: 15 W

Dedicated PC adapter (Ethernet 7):
- PC IPv4: `192.168.1.10`
- subnet: `255.255.255.0`
- gateway/DNS blank

University/ECE adapter (Ethernet 6):
- PC IPv4: `10.24.10.116`
- subnet: `255.255.254.0`
- gateway: `10.24.11.254`

### Hard rule
Do NOT change Ethernet 6, Ethernet 7, firewall configuration, device IP, PC IP, subnet, gateway, DNS, or TCP port. Connectivity is already proven.

## AOS SDK
Installed SDK/runtime:

`C:\Program Files\AOS\OEMPA 1.1.5.4`

Source/header tree:

`C:\ProgramData\AOS\OEMPA 1.1.5.4\Sources`

Important include paths:
- `Sources\Common`
- `Sources\UserHeaders\x64`

Important library path:
- `Sources\UTKernel\x64\Release`

Relevant libraries:
- `UTKernelDriver.lib`
- `UTKernelDriverOEMPA.lib`
- `win_stub.lib`
- `User32.lib`

Runtime DLLs include `UTKernelDriver.dll`, `UTKernelDriverOEMPA.dll`, `UTCustomizedDriverAPI.dll`, `UTKernelAPI.dll`, `UTCalculator.dll`, and others.

The AOS API is largely a Microsoft C++ ABI. Do not replace the native C++ bridge with guessed ctypes calls to mangled C++ methods.

Medium-level AOS APIs are generally preferable for configuration because they reduce the chance of omitting required firmware parameters. Low-level APIs are useful for diagnostics/readback.

## Python/build environment
Python:

`<python>`

Known version: Python 3.14.x 64-bit.

Visual Studio 2022 Build Tools x64 is installed.

Known DLL build command:

```bat
cd /d <repository>\bridge

cl /nologo /EHsc /LD /Od /MD /D "_WIN64" /D "OEMPA_BRIDGE_EXPORTS" ^
/I "C:\ProgramData\AOS\OEMPA 1.1.5.4\Sources\Common" ^
/I "C:\ProgramData\AOS\OEMPA 1.1.5.4\Sources\UserHeaders\x64" ^
oempa_bridge.cpp ^
/link ^
/LIBPATH:"C:\ProgramData\AOS\OEMPA 1.1.5.4\Sources\UTKernel\x64\Release" ^
UTKernelDriver.lib UTKernelDriverOEMPA.lib win_stub.lib User32.lib ^
/OUT:oempa_bridge.dll
```

`/D "OEMPA_BRIDGE_EXPORTS"` is required so the bridge declarations use dllexport instead of dllimport.

C4091 warnings have previously been harmless if compilation/linking completes with no errors.

## Critical safety constraints
These rules are non-negotiable unless there is clear AOS documentation/source proving a change is required and the user explicitly approves it.

- Do NOT call `EnableFMC()`; the device reports dedicated FMC unsupported.
- Do NOT call `SetUnlockEnableShot()` merely to acquire data. The vendor example does not require this for normal acquisition.
- Do NOT use `OEMPA_WriteFileText()`. An experimental `OEMPA_ReadFileText -> OEMPA_WriteFileText` round trip caused a native access violation. Do not restore or rerun that experiment.
- Keep `configs\backup_original.txt` untouched.
- Never access the hardware/device from inside the acquisition callback.
- Never resize the multi-A-scan callback vector/storage while acquisition callbacks are active.
- Force acquisition OFF before configuration/diagnostic hardware writes unless a test explicitly concerns acquisition.
- Current diagnostics should not transmit ultrasound unless the user explicitly proceeds to an acquisition test.
- Do not run additional PA acquisitions without explicit authorization; the 2600-us Compression/Decimation and RX7 diagnostics are recorded in `Current Development State`.
- Do not change gain simply because a few samples clip.
- Do not claim physical steering direction until probe mapping, wedge/direct-contact setup, and material velocity are verified.

## Device/API facts already verified
### Connection
Vendor connection pattern:
- set IP
- set port
- `SetConnectionState(eConnected, true)`
- disconnect with `SetConnectionState(eDisconnected, true)`

The bridge uses `_SetPort` because Windows macros can interfere with `SetPort`.

Connection has succeeded repeatedly.

### Locking
Use `LockDevice()` before device read/write sequences and `UnlockDevice(...)` afterward. `UnlockDevice` commits pending writes and may itself fail.

### Acquisition callback
The A-scan callback copies `pBufferMax` into local callback-owned storage. It must not call device APIs.

### Standard acquisition configuration previously read
Typical configuration:
- Start: 0 us
- Range: 30 us
- PointCount: 3001
- Sampling rate: 100 MHz
- PointFactor: 256
- Bit size: 8-bit
- Rectification: Signed
- Compression: Compression
- Analog gain: 20 dB
- Digital gain: 0 dB
- Filter index: 1
- TimeSlot: 2000 us

Do not hardcode 3001 or 100 MHz where hardware readback is available; use the actual snapshot/readback.

## FMC status and implementation
The OEM-PA reports:
- dedicated FMC supported: NO
- MultiHWChannel supported: YES

Therefore full matrix capture is implemented through MultiHWChannel acquisition/replay rather than `EnableFMC()`.

### Verified MultiHWChannel strategy
For one transmitter:
- cycle 0: HW acquisition, TX0, store RX0..15, return one selected RX
- cycles 1..15: replay stored RX channels

For full 16x16:
- 16 groups x 16 cycles = 256 cycles
- mapping: `cycle = tx * 16 + rx`

`configs\fmc16_full.txt` was successfully loaded and actual acquisition produced:

```text
Raw shape: (256, 3001)
FMC shape: (16, 16, 3001)
```

Saved data:

`data\fmc16x16.npy`

Do not break this working FMC path while working on PA.

## B-scan / C-scan
Current B-scan is a pulse-echo diagonal extraction from FMC:

`B[e, n] = FMC[e, e, n]`

This is not a mechanically scanned conventional B-scan.

C-scan infrastructure exists but there is currently no physical X/Y scanner. Do not spend time extending C-scan unless asked.

## Probe status
The probe has previously been described from its apparent label as something like `AOS F5-N32-P0.6mm`, suggesting 32 elements, 0.6 mm pitch, around 5 MHz.

This is NOT fully verified. Treat only the 0.6 mm pitch as a current project assumption where the existing PA code already uses it. Do not claim the full probe identity/specification as fact without label/datasheet verification.

The OEM-PA has only 16 TX/RX channels. The exact mapping/subset of a possible 32-element probe still needs physical verification before interpreting steering direction.

## Phased-array focal-law implementation
`oempa/focal_law.py` computes ideal geometric steering delays and separately quantizes TX and RX delays.

Known AOS hardware delay resolutions from documentation:
- TX delay step: 4 ns
- TX maximum: 32.764 us
- RX delay step: 5 ns
- RX maximum: 40.955 us
- reception focal TOF step: 20 ns

Current steering relation uses centered element positions and relative delay proportional to:

`x * sin(theta) / c`

then shifts the minimum delay to zero.

At 0 degrees all steering delays are zero.

At +30 degrees with pitch 0.6 mm and velocity 5900 m/s, the generated TX and RX arrays have already been verified through hardware readback.

### PA configuration
`oempa/pa_config.py` generates normal PA mode:
- CycleCount = 1
- dedicated FMC disabled
- MultiChannel disabled
- 16-element TX aperture
- 16-element RX aperture
- TX delay array quantized to 4 ns
- RX static delay array quantized to 5 ns
- reception focusing = Standard
- one focal law

AOS config array conventions:
- aperture uses `Element.count`
- TX delay: `Delay.count=16;1`
- RX delay is a 2-D element x focal-law array; with one static focal law it is `Delay.count=16;1`

## PA validation already completed
The following were successfully verified before the current issue:

1. Python focal-law calculation.
2. AOS text configuration generation.
3. Offline `OEMPA_ReadFileText` parsing.
4. 0-degree hardware configuration/readback.
5. +30-degree hardware delay readback.
6. TX delay values match 4 ns quantization.
7. RX delay values match 5 ns quantization.
8. 16-element TX/RX apertures read back correctly.
9. Standard RX focusing read back correctly.
10. One real 0-degree PA beamformed A-scan was acquired and saved.

The real 0-degree PA A-scan had:
- shape `(3001,)`
- dtype/intended data size: signed 8-bit
- min -113
- max +127
- sampling interval 0.01 us
- record 30 us

However, the saved waveform had meaningful/nonzero data only until about 1.93 us and then an exact-zero tail through the remainder of the record. Do not yet interpret early peaks as specimen echoes.

An A-scan configuration diagnostic compared PA and known-good FMC settings and found no differences in the checked A-scan controls, including enable/request/buffer/range/point count/sampling/bit size/filter. Therefore do not randomly change those A-scan controls to address the zero tail.

## PA configuration-load history

`pa_test_0deg.txt` parses successfully with `OEMPA_ReadFileText`, but a later attempt to load it through `OEMPA_ReadFileWriteHW(..., eAcqOff)` failed.

A load-stage callback diagnostic showed:

```text
Entered ReadFileWriteHW: True
Reached before HW write: True
Reached after HW write: False
Reached load exit: False
Parsed cycle count: 1
```

Therefore the failure occurs during `OEMPA_WriteHW` / hardware update, not text parsing.

A focal-law setter diagnostic then programmed the intended 0-degree fields individually. The individual setter calls reported PASS, but the AOS/UTKernel displayed a critical error indicating:

```text
maximum pulser power is 15 Watts
required power is 17.49 Watts
```

The vendor message says the condition can be addressed by increasing TimeSlot, decreasing PulseWidth, or decreasing aperture.

This is currently the strongest explanation for why the full AOS configuration write can fail even though the individual focal-law setter calls succeed.

The candidate `configs\pa_test_0deg_timeslot_2600us_estimate.txt` was generated from the verified 0-degree configuration by changing only TimeSlot to 2600 us, then passed offline parsing. It was subsequently loaded in the approved controlled hardware test recorded in `Current Development State`; acquisition remained OFF.

## Pulser-power APIs discovered
AOS header `UTKernelDriverOEMPA.h` exposes:

```cpp
double GetPulserPowerMax() const;      // Watt
double GetPulserPowerCurrent() const;  // Watt

double GetPulserPower(
    int iCycleCount,
    structOEMPACycleParameter *aCycleParameter
) const; // Watt
```

OEMPATool itself reads the current/max values using:

```cpp
double dPulserPowerMax =
    m_pHWDeviceOEMPA->GetSWDeviceOEMPA()->GetPulserPowerMax();

double dPulserPowerCurrent =
    m_pHWDeviceOEMPA->GetSWDeviceOEMPA()->GetPulserPowerCurrent();
```

The installed header declares `GetPulserPower(int, structOEMPACycleParameter*) const`, returning watts. Its input struct contains only `DWORD m_dwTimeSlot`, `DWORD m_dwPulserCount`, and `float m_fPulseWidthMax`; the header does not state their units or how to populate them. A source-tree search found no estimator call site, struct construction/population, or implementation body. The body appears to be supplied by the SDK binary, so the `const` declaration alone does not prove it has no side effects.

Vendor documentation provides the physical relationships but not this struct's encoding:
- `2_Hardware_Introduction.pdf`, section 7, says average pulser power depends on aperture, pulse width, and TimeSlot; TimeSlot is `1/PRF`; pulse width is `(1 / probe frequency) / 2`. It says an over-limit error disables pulsers and recommends fewer elements, narrower pulse width, or a longer TimeSlot.
- `7_Software_Functions_&_Parameter_List.pdf` describes `SetTimeSlot`/`GetTimeSlot` as a `double` cycle duration, minimum 50 us and 10 ns step. It describes emission pulse width as a `float` in seconds, 4 ns step, applied to elements within the cycle aperture.
- `UTCustomizedWizardAPI/CustomizedWizardAPI.cpp` calculates wizard pulse width as `0.5 / probe frequency`, calls `CheckEmissionWidth`, and assigns that width for each focal-law element. This does not show how the three `structOEMPACycleParameter` fields are derived.

Therefore the manuals support understanding the physical dependencies and API-level quantities, but do not establish that the struct fields are direct copies of those values. Do not construct estimator inputs by guessing units, conversions, aperture counting, or aggregation semantics.

The completed `tests.test_pulser_power` diagnostic connected to the device, disabled acquisition, read both values, disabled acquisition again, and disconnected. Exact output:

```text
[OK] Connected
[OK] Acquisition disabled
PulserPowerMax: 15.00 W
PulserPowerCurrent: 0.02 W
[SAFE] Acquisition is OFF
[OK] Disconnected
```

No configuration was loaded or changed during this diagnostic.

Further source investigation found:
- `UTKernelDriverOEMPA.h` declares public `const` method `GetPulserPower(int, structOEMPACycleParameter*)`, returning watts.
- The struct contains only `DWORD m_dwTimeSlot`, `DWORD m_dwPulserCount`, and `float m_fPulseWidthMax`; the header does not document their units or how they are derived from a candidate configuration.
- Searches of the complete installed textual SDK source and headers found no call site for `GetPulserPower`, no code creating/populating the struct, and no exposed implementation of the estimator or the reported 17.49 W validation. No `PulserCount` or `PulseWidthMax` member uses were found. `.TimeSlot` appears in unrelated API/wizard code, but no use was found that populates `structOEMPACycleParameter`.
- `OEMPATool` uses the current/max getters for its hardware-information display. The exposed `OEMPA_WriteHW` source contains configuration writes but does not call `GetPulserPower` directly.
- The installed AOS PDFs were text-extracted and searched. They document the physical power dependencies and API-level units below, but do not mention `structOEMPACycleParameter`, `GetPulserPower`, or the struct member names.
- The hardware manual states average power depends on aperture, pulse width, and TimeSlot; defines TimeSlot as `1/PRF` and pulse width as half the probe period; and recommends reducing aperture/pulse width or increasing TimeSlot when over limit. The function/parameter list specifies API TimeSlot as a `double` duration (minimum 50 us, 10 ns step) and emission pulse width as a `float` in seconds (4 ns step) for the cycle aperture. These API semantics do not define the separate `DWORD`/`float` encodings or aggregation used by `structOEMPACycleParameter`.

## Current Development State

### FMC acquisition-speed issue solved / production closeout - 2026-10-15

Active checkpoint: operator hardware benchmark accepted; acquisition-speed issue SOLVED for verified full16x16 FMC. No hardware connection/read/write/acquisition, parameter/network change or new dataset occurred during this closeout. Measurements below are operator-reported real OEM-PA results, explicitly distinct from synthetic/offline test durations. Historical pending-benchmark notes remain evidence and are superseded by this checkpoint.

Before -> After: full_snapshot35.1942s ->0.7579s; preparation35.3665s ->0.9154s; first_frame0.5078s ->0.5079s; total36.1138s ->1.6321s. Total reduced approximately95.48%,22.13x faster; actual frame acquisition remains~0.508s. Full-snapshot lock/unlock counts528/528 ->1/1; optimized Flush2 calls. Reported batch Unlock0.1290s, Flush total0.4000s; Lock duration not supplied. Additional after stages: initial_OFF0.0047s, topology_refresh0.1251s, Python verification0.0176s, storage_OFF0.0095s, SDK_ON0.0332s, first-callback latency0.0331s, shutdown_OFF0.0281s, copy/validation0.0027s, cube0.0001s, metadata0.0013s, GUI render0.0878s. These intervals overlap where defined; no fabricated Lock duration or summed stage total.

Operator reports accepted256/256 first-frame cycles,13 post-frame callbacks during shutdown,0 unexpected/0 malformed; FMC(16,16,3001), amplitude-128..127,562/768256 int8 representation-limit samples(0.0732%). No physical interpretation or gain adjustment. Physical firing count Unknown, physical mapping unverified. Save/reload outcome for this particular run was not supplied, so none is claimed. User-supplied numbers are recorded in docs/fmc_timing.md with complete before/after table.

Production default confirmed offline: source routes eligible approved full16x16 FMC to fresh batch readback automatically on Apply and Acquire; api loads bridge/oempa_bridge.dll and default build outputs that filename. Static PE export parsing confirmed OEMPA_GetFMCSnapshotBatch in runtime/default DLL and candidate, without loading either DLL or device APIs. No replacement/rebuild/process disturbance needed. Full256-cycle verification,16 base TX reads, SDK-unreadable mixed provenance, dirty/stale/reconnect safeguards and failure cleanup remain unchanged. No cached/partial verification; no callback/first-frame/post-frame/shutdown behavior or parameter changes. Compatibility for missing old-DLL export remains; a failed supported batch never falls back.

GUI cleanup only: remove routine [TIMING] success/failure dumps and verbose successful FMC timing/revision/amplitude-stat lines; one concise completion includes shape, accepted first-frame count and shutdown count when nonzero. Preserve actual errors, nonzero post-frame unexpected/malformed warnings, chronology overflow and representation-limit notices. Preserve every detailed timing/warning/counter in metadata/sidecar and backend diagnostics; first subsequent draw is still measured, no numerical/metadata provenance removed. A-scan/PA unchanged. Files modified: gui.py, tests/test_ui_phase3.py, docs/fmc_timing.md, AGENTS.md. Tests assert quiet timing finalization while metadata and source bytes remain intact, and concise accepted-frame reporting. Final regression: <python> -m unittest discover -s tests -p 'test_ui_*.py' -q247 passed; <python> -m unittest discover -s tests -p 'test_tfm_offline.py' -q27 passed. Complete inspected offline suite274 passed, preserving baseline. Existing SDK-free native harness cases ran through that suite; no native source/build change needed. GUI regressions now assert quiet timing finalization with metadata/warnings preserved, concise normal completion, and visible nonzero post-frame/chronology warnings. Two Python AST syntax checks and repository_audit.py passed. All48 original config/data hashes unchanged. No unrestricted hardware-capable test discovery. Supplemental desktop validate_gui_usability_offline.py stalled in its first Device capture/root.update; no hardware imported. Sent a normal CloseMainWindow ONLY to the verified command-line-matched offline test process (not production GUI), clean_close=true. The interrupted screenshot then raised expected application-destroyed winfo error; this supplemental run is NOT counted as passed. No unrelated layout changes were made. Complete274-test offline regression remains passed. STOP; speed issue closed from supplied hardware evidence, no additional acquisition authorized/performed.


### FMC batched OFF readback completed offline - 2026-10-15

Active checkpoint: STOP before manual hardware benchmark. No device connection/access/configuration write/acquisition, network/parameter change, new hardware data or DLL hot replacement. Operator-supplied second profile establishes full_snapshot35.1942s/preparation35.3665s/first_frame0.5078s/total36.1138s. Four snapshot Lock/Unlock totals sum34.7329s from supplied rounded values (~98.69% of snapshot); no new hardware measurement or speedup is claimed.

Vendor evidence: installed Software_API4.3.4.1-4.3.4.3 printed pages30-32 explicitly supports asynchronous parameter reads in one lock, with pointer outputs valid through Flush/Unlock. Flush completes pending requests without releasing ownership. eAcqDefault may enable pulser according to software defaults, so batch lock AND unlock explicitly use eAcqOff; no default-setting setter called. UTKernelDriver.h617-629 gives lock/flush contract. Installed CustomizedDriverAPI.cpp OEMPA_ReadHW locks around1912, resolves topology via Flush before allocation, loops all cycles around2213, invokes normal/MultiHWChannel read helpers and unlocks around2251. ReadHWWriteFileMultiHWChannel around1832 queues emission width/delay/aperture or receive start/aperture/decimation with caller-held lock; no private lock lifecycle is shown there. Getter implementations remain binary but the exposed vendor callers establish intended multiple-cycle/MultiHWChannel use. No SDK source/manual copies added to distribution.

Added shared bridge/fmc_batch_readback.h template, instantiated by real AOS types/device and SDK-free deferred-output fake. Fixed256-cycle owner retains every scalar/enum/aperture/array/count/capacity output until OFF unlock, no pending-buffer resizing. One explicit OFF lock, fresh topology read +Flush, all256 normal+256 MultiHW outputs +Flush before flag-dependent reads, all16 independent base TX width/delay outputs, one OFF unlock, then local sampling/aperture/count decoding. Conditional TX reads are additionally retained if completed classification outputs ever supply true; known current SDK classification still decodes unavailable, never False/hardware verified. Nothing publishes until every operation/unlock/decoding succeeds. RAII attempts exactly one OFF unlock on getter/Flush failure or exception; lock failure performs no reads/unlock. Failed/throwing unlock rejects the whole snapshot, with no partial/cached fallback. A failed batch retains one bounded output owner on the context until handle destruction, declared before the SDK device so outputs outlive its destructor; later batches on that handle refuse rather than reset uncertain buffers. Successful output releases its owner only after OFF unlock/decoding/publication. Offline tests cannot prove physical driver lock release after a real communication-failed unlock; treat this as uncertain, abort acquisition and use normal cleanup/diagnosis, never guessed force-unlock retries.

Additive OEMPA_GetFMCSnapshotBatch export validates exact256/16 grouping, checks connected/support, allocates stable owner and returns complete normal/multi/base TX arrays/topology only on success. Existing exports remain available. Python shares unchanged normal/extended decoders and routes only exact approved full16x16 FMC with valid applied-file provenance through the batch. HardwareSnapshot field assembly and verify_configuration logic/coverage are unchanged. Fresh batch topology must match initial fresh topology. Only missing old-DLL export returns None and retains full legacy reads; supported export failure never retries or substitutes GUI/cache state. Apply and Acquire both retain full verification, dirty/stale/reconnect protection and mixed-source exception rules. SettingId not used. A-scan/PA/other FMC retain their native read paths; only pure decoder extraction is shared.

Detailed preparation timers retained: new FMCBatch.LockDevice/UnlockDevice/Flush/getter entries include counts,total,max. Full snapshot has one lock pair/two Flush calls; separate initial OFF/topology/storage OFF and final acquisition OFF are unchanged, so whole preparation still has additional pairs. No callback, native first-frame, acquisition/shutdown behavior, raw storage, dataset mapping, probe assumptions or parameters changed. Cancellation checked before/after synchronous native batch and during Python assembly; close waits for worker, no interruption of an SDK call or device destruction while locked.

Tests were written/executed before production routing: thirteen native cases pass for deferred pointer outputs/full field coverage, lock failure, getter false/throw, Flush failure, unlock false/throw/pending-output failure, topology mismatch, sampling error, invalid counts, unchanged SDK TX outputs and functional classification flags. Fake asserts explicit OFF/ownership on each hardware getter, counts3618 queued reads in current SDK model, all256 normal/MultiHW and16 TX calls, stable outputs and no held fake lock. The uncertain-unlock case retains pending writes until simulated SDK teardown drains them while the owner is still alive. Python compares entire legacy/batch HardwareSnapshot and VerificationReport/evidence, still rejects readable cycle255 mismatch, rejects native failure/topology change without legacy retry, tests old DLL compatibility, cancellation, PA/no-provenance isolation and fake-ctypes types/order/count/unavailable decoding. Existing callback immutability/no-device-access, shutdown/OFF failure, metadata/raw-array tests continue passing.

Files created: bridge/fmc_batch_readback.h, tests/fmc_batch_readback_native.cpp, tests/build_fmc_batch_readback_test.cmd, tests/test_ui_fmc_batch_readback.py. Modified: bridge/oempa_bridge.cpp/.h, oempa/api.py (shared decoders/additive wrapper), oempa/hardware_state.py (fresh-batch adapter only), tests/test_ui_native_wrapper_offline.py, README.md (new SDK-free harness build), docs/fmc_timing.md, AGENTS.md. Candidate bridge/oempa_bridge_batch.dll built successfully via cmd /c bridge\build_bridge.cmd oempa_bridge_batch.dll with existing C4005/C4091 warnings only. Runtime default not replaced and processes not closed. All three native harness build commands (build_fmc_batch_readback_test, build_callback_order_test, build_fmc_first_frame_test) succeeded, no SDK linkage in test executables.

Final safe validation with <python>: -m unittest discover -s tests -p 'test_ui_*.py' -q247 passed; -m unittest discover -s tests -p 'test_tfm_offline.py' -q27 passed; total274 preserves262 plus12 new test methods (native method covers13 cases). Four changed Python syntax/AST checks passed; fresh hardware_state import loads no api/driver. repository_audit.py passed. All48 original config/data SHA256 hashes unchanged, including fmc16_full.txt/backup_original.txt. Hardware-capable general discovery excluded. Disconnected desktop validate_gui_usability_offline.py passed18 layouts at1300x820/1100x700,hardware_imported=false/clean_close=true/errors empty. validate_tfm_production_offline.py --output artifacts/fmc_batch_tfm_offline_review passed9 layouts, sdk_loaded=false/raw_unchanged=true/clean_close=true. Synthetic review artifacts retained locally/ignored. No hardware validation performed.

Next manual procedure is detailed in docs/fmc_timing.md: Stop/Disconnect/Close GUI, rebuild default DLL, connect/apply unchanged hash-matched fmc16_full.txt while OFF and require full mixed-source Verified. Any SDK/readback error STOP. Only under explicit operator approval, one normal acquisition with identical previous settings, validate/save new dataset/sidecar/reload then disconnect. Compare full_snapshot/preparation/first_frame/total and native FMCBatch counts1lock/1unlock/2Flush plus all getter counts against operator baseline. Device queue limits, real asynchronous behavior, latency and real unlock-failure cleanup remain untested with this candidate. No speedup estimate, no automatic acquisition/retry, no B-scan/TFM hardware acceptance authorized by this checkpoint.

### FMC preparation investigation - offline instrumentation completed 2026-10-15

Active checkpoint: STOP offline before hardware measurement/optimization. User reports preparation=35.0121s. Existing data sidecars do not provide its detailed timing breakdown. No OEM-PA access/connection/configuration write/acquisition, network or acquisition parameter change occurred. No measured SDK-call attribution or speedup is claimed.

Source trace: preparation starts at worker_start and ends before acquisition.start. It includes explicit OFF, fresh CycleCount/MultiHWChannel topology,528 native snapshots (256 normal +256 MultiHW +16 independent base-cycle TX), snapshot assembly/derived start processing, full Python verifier, second OFF during callback preparation, count/reset/registration when needed/clear/preallocation and chronology/frame arming. Full verification on Apply and every Acquire remains unchanged, including dirty/stale/reconnect/uncertain paths. No cached verification fast path or ignored getter/mismatch was introduced. First-frame admission/immutable copies/post-frame classification, wakeup, ON/OFF path, shutdown/publication and A-scan/PA behavior remain unchanged.

Added bridge/preparation_timing.h: opt-in thread-local fixed64-entry aggregate count/total/max nanosecond collector, no per-cycle logs/allocations. Existing selected OFF/topology/normal/extended snapshot SDK expressions are timed independently, including LockDevice and UnlockDevice. Original call arguments/order/short-circuit/results/exception handling remain intact. Timing RAII also records calls that throw. No instrumentation in the acquisition callback. Additive Begin/End/GetPreparationTiming exports touch local state only; reset/collect on the owning worker and disable before ON. Python wrappers decode bounded tables with explicit overflow/error. Missing old-DLL exports warn without skipping hardware verification or inventing timings. Header native statistics tests cover aggregate/max/capacity/overflow and exception cleanup.

FMCTiming now retains preparation_stages_s (OFF/topology/full_snapshot/python_verification/storage OFF/count/register/clear/allocation/arming) and preparation_sdk by off_readback/storage phase and export.method. Aggregate GUI summary adds stage times and five largest SDK totals; complete tables persist through existing timing_profile metadata. Existing saved cube/provenance untouched. Python and native times are inclusive/differently scoped; do not add overlapping observations or attribute deferred unlock work to a particular getter without evidence. Diagnostic collection overhead remains part of preparation, not silently subtracted.

Reuse conclusion: not yet shown safe with current interfaces. AOS UTKernelDriverOEMPA.h exposes GetSettingId(DWORD*), swGetSettingId and SetSettingId. Software_API callback docs state application setting software assigns the identifier. CustomizedDriverAPI.cpp optional setting-ID callbacks explicitly call SetSettingId during read/write workflows. Therefore this ID is not established as an automatic complete configuration revision/checksum; software cached ID and unchanged CycleCount/MultiChannel cannot prove unchanged gain/timing/aperture/filter. IsAcqStatusEnabled is a software flag, not a substitute for successful explicit OFF. Do not implement cache reuse on those assumptions. A future policy requires trustworthy complete mutation detection or an explicit accepted exclusive-control assumption, session/mode/request/hash/revision match, no uncertainty and successful fresh OFF/safety checks, while preserving full Apply verification and honest historical-vs-fresh provenance. No new SettingId write or getter experiment performed.

Modified: bridge/oempa_bridge.cpp/.h, oempa/api.py/timing.py/acquisition.py/gui_backend.py, tests/fmc_first_frame_native.cpp, tests/test_ui_timing.py/test_ui_native_wrapper_offline.py/test_ui_backend_offline.py, docs/fmc_timing.md, AGENTS.md. New: bridge/preparation_timing.h. Built candidate bridge/oempa_bridge_preparation.dll with cmd /c bridge\build_bridge.cmd oempa_bridge_preparation.dll: success, existing C4005/C4091 warnings only. Candidate is not runtime default; running processes/DLL not replaced. Operator must Stop/Disconnect/Close GUI, rebuild default before collecting detailed timings. cmd /c tests\build_fmc_first_frame_test.cmd: SDK-free build passed; synthetic native integrity tests execute this harness.

Validation: <python> -m unittest discover -s tests -p 'test_ui_*.py' -q:235 passed. <python> -m unittest discover -s tests -p 'test_tfm_offline.py' -q:27 passed. Total262 preserves255 baseline plus7 focused tests. Cases cover measured success/failure return behavior, cleanup on error, missing profiling exports, bounded top-five summary, nanosecond/count decoding, overflow/failure, nested timing metadata roundtrip and unchanged verified-request fresh all-cycle readback. Existing external-mismatch rejection and frame/shutdown regressions pass. Seven changed Python files AST-checked; fresh timing import is SDK-free. All48 original config/data hashes unchanged; backup_original.txt/fmc16_full.txt untouched. Only inspected safe offline discovery patterns ran; no hardware-capable diagnostics/general discovery.

Next: collect preparation_stages_s/preparation_sdk from a separately explicitly authorized production hardware attempt with unchanged verified settings, or review an operator-supplied profile. No such attempt authorized/performed here. Determine whether OFF, topology, getter, LockDevice, UnlockDevice, Python verifier or storage actually dominates before selecting redundant calls. 35.0121s aggregate alone cannot support a targeted optimization. Full verification remains in force.

### Distribution cleanup and FMC timing completed offline - 2026-10-15

Active checkpoint: STOP offline. No device connection/access, hardware write/acquisition, network/configuration parameter change, new dataset, Git commit/push or performance optimization. Source/distribution review and additive measurement are complete; actual 9-10 second hardware latency remains unmeasured. Full OFF readback/verification on Acquire and all immutable ordered first-frame/early-error/post-frame safety behavior remain unchanged. Callback adds only local bounded first-wins QPC observations, no SDK/file/Tk access or active resizing. A-scan/PA behavior unchanged.

Added README.md, requirements.txt, .gitignore, scripts/setup_msvc.cmd, tools/repository_audit.py and docs/fmc_timing.md/repository_cleanup.md/cleanup_manifest.json. Build/runtime paths accept OEMPA_AOS_RUNTIME, OEMPA_AOS_SOURCES, OEMPA_VCVARS and alternate OEMPA_BRIDGE_OUTPUT; 35 historical diagnostic/generator scripts now derive repository paths instead of a personal username. Historical AGENTS personal checkout/interpreter paths sanitized to placeholders, preserving recorded evidence. No packages installed or external environment changed. Source tree/install/build/run/test/dependency/license guidance is in README. Vendor SDK/DLL/manual extracts, datasets/sidecars, historical hardware artifacts and generated configs remain locally preserved/ignored. No .git exists, so history/index were not inspectable. Audit of source candidates found no selected credential/private-key/personal-path patterns; not an exhaustive security guarantee. No public license assigned; obtain AOS redistribution authorization independently.

Removed 92 obsolete synthetic review/build files listed in docs/cleanup_manifest.json, plus reproducible Python cache files listed there after final validation. Retained runtime DLLs, offline native harness executables, useful source/tests, every original config/data file and historical hardware evidence. All 48 original config/data SHA256 hashes match before-cleanup inventory. In particular fmc16_full.txt remains0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7; backup_original.txt untouched. Ambiguous/user-edited generated configs retained rather than assumed obsolete.

New oempa/timing.py and bridge/fmc_timing.h retain per-attempt Python perf_counter and seven native QPC timestamps. Additive bridge export/ctypes wrapper expose local clock observations only. Backend/acquisition/GUI record request, worker start, OFF snapshot/verification, preallocation, ON SDK entry/return, first valid callback, completed final copy, worker OFF request, OFF entry/return, record-copy validation, cube/metadata completion, GUI delivery/update and first subsequent draw. First-wins counters and existing frame evidence distinguish accepted/pre-error/post-frame/invalid callbacks. One aggregate timing line, no callback log flooding. Optional timing_profile sidecar metadata round-trips, older sidecars stay compatible. Missing/native-clock-incompatible timings remain unavailable with warnings, never fabricated zeros. Stage durations may overlap if callbacks precede ON return. Physical firing count remains Unknown.

Vendor evidence: inspected installed AOS1.1.5.4 headers/CustomizedDriverAPI.cpp and Software_API sections6.1/6.3.2/6.3.4/6.4/6.5.4/6.6.2 plus parameter-list cycle section. Parallel HWAcq stores simultaneous receiver channels; replay processes saved data without transmission. Approved table has16 HWAcq entries and240 replay entries, not256 pulse-bearing entries. This does not establish actual firing count under continuous ON/OFF. Vendor write path applies TimeSlot to each logical cycle and serializes HWAcquisitionTime/HWReplayTime;256x2000us nominal table sum0.512s excludes SDK/transport/readback/shutdown/display overhead. Dedicated-FMC timing is a separate unsupported branch, not used. No TimeSlot change. Details, sources, honest before/after pending table and exact separately authorized manual benchmark steps in docs/fmc_timing.md.

Native build: cmd /c bridge\build_bridge.cmd compiled but default output was locked (LNK1104); no running process was closed/disturbed. cmd /c bridge\build_bridge.cmd oempa_bridge_timing.dll succeeded with existing vendor C4005/C4091 warnings. Candidate DLL is NOT installed as runtime default. Operator must safely Stop/Disconnect/Close GUI, then rebuild default DLL before manually collecting timings. Both cmd /c tests\build_callback_order_test.cmd and cmd /c tests\build_fmc_first_frame_test.cmd succeeded; harnesses are SDK-free. Tests cover first-wins timestamps, overlapping ON/callback chronology, unavailable clock/missing OFF/draw observations, full cube persistence/mapping, immutable evidence and no callback device/file access. Existing integrity/stop/cancellation regressions remain passing.

Final commands with <python>: -m unittest discover -s tests -p 'test_ui_*.py' -q:228 passed; -m unittest discover -s tests -p 'test_tfm_offline.py' -q:27 passed. Total255, preserving247 baseline plus8 focused cases. AST syntax passed all110 Python sources; pure timing/dataset imports load neither oempa.api nor driver. tools/repository_audit.py passed. No unrestricted hardware-capable test discovery. Disconnected tools/validate_gui_usability_offline.py passed18 layouts at1300x820/1100x700, no errors, hardware_imported=false, clean_close=true. First concurrent tools/validate_tfm_production_offline.py run timed out after four valid layouts; isolated repeat (--output artifacts/distribution_tfm_offline_review_retry) passed all9 layouts with clean close, sdk_loaded=false/raw_unchanged=true. No application change was made to mask timeout. Review outputs retained locally/ignored.

Remaining: no actual timing baseline or speedup can be claimed; no source of the operator-observed9-10s delay yet established. Repeated OFF readback is a candidate, not a measured bottleneck. No safety readback/copy/validation omitted. Next action requires independent explicit operator hardware authorization, deployment of the built timing bridge, one normal approved FMC attempt and inspection of timing_profile. Do not automatically acquire/retry or optimize without measurements.

### TFM plot layout correction completed - 2026-10-15

Active checkpoint: narrowly scoped TFM GUI layout improvement completed and validated offline; STOP. Read latest instructions/checkpoint and inspected TFM container/canvas packing, resize handling, aspect/layout/colorbar interaction and installed Matplotlib toolbar implementation. No OEM-PA access/connection/configuration write/acquisition, native build or network change. No TFM core/math, reconstruction parameters, normalization, FMC data/acceptance, A-scan/PA, controller/state or safety behavior changed.

Root cause: Tk image_panel/canvas already use fill=both/expand=True and receive actual resized dimensions; figsize=(7,4) is initial sizing only. Tight layout with equal-aspect axes plus automatic colorbar allocation caused a badly off-center axes group and excessive margins. SDK-free Agg reproduction at904x302: image167.7x192.9px, image/bar center657px versus canvas center452px. At704x212: image89.5x102.9px, group center528.9px versus canvas center352px. This was not a missing grid weight or fixed-size Tk canvas. Installed NavigationToolbar2Tk deliberately reserves50px for stable two-line coordinate messages; that reservation was inspected and preserved instead of replacing it with arbitrary heights.

Fix: TFM figures alone use Matplotlib compressed constrained layout from construction through rendering. Colorbar uses relative fraction0.04,pad0.02,aspect30; shortened labels retain display-only meaning and fit minimum height. No explicit axes coordinates/pixel offsets or physical-coordinate stretching. Equal aspect, x bounds, inverted depth, labels/title/velocity, existing toolbar, top controls and settings scrolling remain intact. Other workspace figures retain tight layout. Natural horizontal letterboxing remains where a wide/short canvas is height-limited by the physical x/z ratio; filling that whitespace would distort geometry.

Final real-Tk measurements: normal canvas904x302, image186.6x214.6px, group center451.2px versus452px (0.09% offset). Minimum full-width canvas704x212, image108.3x124.6px, group center347.3px versus352px (0.66% offset). Settings-visible minimum canvas429x212 fits image/colorbar/labels with1.24% center offset. Image height grows approximately11% normal/21% minimum relative to reproduced old layout. Colorbar is7.2px normal/4.2px minimum and immediately adjacent. Figure uses available height while preserving the20:23 physical ratio for the default region. Resize responds to actual canvas dimensions, not fixed figure dimensions.

Files modified: ui/workspace.py (TFM-only layout engine), ui/tfm_workspace.py (layout/colorbar/labels only), tests/test_ui_tfm_offline.py (one geometry/resize regression), tools/validate_tfm_production_offline.py (optional --output and measured geometry/text/aspect checks), AGENTS.md. No new production module or backend edit. New synthetic-only artifacts/screenshots/report are isolated in artifacts/tfm_plot_layout_offline_20261015; earlier artifacts/historical data/configs remain untouched. Existing synthetic validation fixture raw bytes are unchanged through reconstruction/display/save/reload; no real FMC dataset was modified.

Validation with <python>:
- -m unittest discover -s tests -p 'test_ui_tfm_offline.py' -q:19 passed.
- -m unittest discover -s tests -p 'test_ui_*.py' -q:220 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q:27 passed. Complete safe offline total247 preserves246 baseline plus one new regression. Hardware-capable general discovery was excluded.
- -m py_compile ui/workspace.py ui/tfm_workspace.py tests/test_ui_tfm_offline.py tools/validate_tfm_production_offline.py: passed; fresh UI import loads no oempa.api/driver; four-file whitespace checks passed.
- tools/validate_tfm_production_offline.py --output artifacts/tfm_plot_layout_offline_20261015: exit0 on desktop with pre-import fake backend forbidding device operations. Nine cases at1300x820/1100x700 cover current/offline synthetic FMC, settings shown/hidden/scrolled, normalized/dB, stale status and cooperative close during reconstruction. New assertions measure centering, useful image height, narrow adjacent colorbar, unaltered physical aspect, unclipped x/depth/title/velocity/colorbar labels, full canvas width and bounded native toolbar height. No layout issues/tracebacks; sdk_loaded=false,clean_close=true,raw_unchanged=true. Screenshots visually reviewed. Existing sandbox Tcl limitation handled by established desktop execution only; no environment change.

The new Agg regression also exercises three figure sizes and repeated display modes, proves preserved x/depth bounds and aspect, no reconstruction invocation on redraw, stable result identity and byte-identical numerical image. STOP after offline layout validation; no further hardware or reconstruction-feature work authorized.

### Production homogeneous TFM completed - 2026-10-15

Active checkpoint: offline processing/UI implementation and validation complete; STOP before hardware access. User reports successful manual A-scan/current16x16 FMC/first-frame/view/diagonal/B-scan tests and a delayed response moving later with reflector distance. Supplied FMC observations:16x16x3001,100MHz,start0us,range30us,logical0-15,AOS-defined elements1-16,pitch0.6mm; physical wiring not independently tested. These are user-reported observations, not a new agent-run hardware test or an independent interpretation. No OEM-PA access/connection, hardware configuration load/write, acquisition, native build or network change occurred. Repository baseline233 (not attachment's older220) is preserved. Acquisition modes remain exactly A-scan/FMC/Phased Array; TFM is offline processing only.

Reused existing oempa/tfm.py numerical loop unchanged: x_e=(e-(N-1)/2)*pitch, d_e=hypot(x-x_e,z), t_ij=(d_i+d_j)/c, q=(t_ij-start_s)*sampling_hz, I(x,z)=sum over ALL TX/RX pairs of temporally interpolated signed FMC[i,j,q]. Linear interpolation is now the production UI default; existing explicit nearest option/public API remains compatible. Out-of-record paths contribute zero, exact last samples are safe, and no calibration offset, acoustic-zero correction, per-trace rectification or diagonal-only sum was introduced. Float64 coherent image and centered coordinates remain read-only; chunked NumPy cancellation/progress and existing serialized controller worker are retained. No GPU/dependency added.

Active geometry derives from cube axes, never the full probe label's32 count. Dataset probe-description pitch is prefilled with its label/user provenance; missing/invalid pitch requires explicit entry. Current GUI Probe defaults are never silently substituted. New source selection clears previous pitch/legacy-rate/start assumptions. For16x0.6mm the UI/core retain -4.5..4.5mm coordinates and9mm center span. AOS-documented logical0-15->elements1-16 mapping and Not independently tested wiring remain distinct; geometry is not claimed physically calibrated. Complete captured timing is authoritative and locked; legacy data still needs explicit rate AND start with separate assumption provenance. Source metadata is never rewritten to fabricate readback truth.

TFM tab has persistent Experimental/Homogeneous-medium/signed-callback caveats; Open FMC/Use current/Save result/display controls; grouped, scrollable TFM Input/Propagation/Image region/Resolution/Missing timing settings beside the image, with mouse-wheel/scrollbar support and a pinned reconstruct action. Defaults: x-10..10mm,z2..25mm,201x231,linear,normalized absolute display. Velocity starts blank; Water example1480m/s is an explicit convenience button, never automatic material detection. Captured shape/count/rate/start/revision, metadata pitch source, documented mapping and separate wiring status are visible. Settings can hide after completion for plot space. Axes retain mm, physical aspect and increasing positive depth downward from z=0 at the array reference plane. Title identifies Experimental TFM - Homogeneous Medium and velocity. Raw/Absolute/Normalized/dB display processing never overwrites the coherent result or source FMC. Callback MAX/pre-compression RF/phase-fidelity caveats remain visible; bright responses are not identified physically. Reusing the colorbar avoids repeatedly reallocating/subdividing axes on display edits.

Source/parameter staleness is tracked separately from hardware revision. Replacing the main FMC array or its metadata revision marks an existing TFM image stale without recomputing; a detached current-source selection cannot reconstruct until a source is explicitly selected again. TFM offline-file replacement and pitch/velocity/bounds/resolution/method edits increment the local revision and stale the prior result, which retains its original request/source metadata. Display changes/tab switching do not reconstruct, dirty hardware configuration, modify acquisition state or invoke hardware APIs. Existing close/cancellation waits for the owning worker and then normal cleanup; no force-kill or worker Tk call.

Optional Save result uses existing serialized offline file-I/O ownership. Atomic .npz contains unnormalized image,x_m,z_m,element_x_m and Unicode metadata_json, readable with allow_pickle=False. Embedded JSON preserves full source acquisition metadata/config revision/shape/callback representation/field provenance, model, requested geometry/source/pitch/velocity/grid/interpolation, actual-or-assumed timing, element coordinates, documented mapping, wiring status, UTC reconstruction time and experimental limitations. Saving is independent of reconstruction/display and does not touch FMC .npy/sidecars. No generic acquisition persistence or verification policy changed.

Files modified: oempa/tfm.py (additive dataset-geometry/provenance/save helpers; unchanged reconstruction loop), ui/tfm_workspace.py, ui/workspace.py (TFM plot container only), tests/test_tfm_offline.py, tests/test_ui_tfm_offline.py, tests/test_ui_phase3.py (updated TFM heading expectation), AGENTS.md. Created tools/validate_tfm_production_offline.py and artifacts/tfm_production_offline_20261015 with synthetic-only fixture/sidecar, saved TFM result, nine screenshots and validation.json. Existing replacement-source test now explicitly reenters missing pitch rather than inheriting another dataset's assumption; original test purposes/assertions retained. No gui.py/acquisition/driver/API/bridge/config builder/FMC acceptance/Stage3C verification/BScanProcessor/PA/network or historical data edited. fmc16_full.txt SHA256 rechecked unchanged:0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7; backup_original.txt untouched.

Final validation with <python>:
- -m unittest discover -s tests -p 'test_ui_*.py' -q:219 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q:27 passed. Total246 preserves all233 baseline plus13 new cases. Only inspected pure/fake/native-synthetic offline patterns ran; unrestricted discovery/hardware-capable diagnostics were excluded.
- New numerical cases verify16-element endpoints/spacing, metadata-vs32-element probe count, absent/invalid pitch, independent distance/start/sample-coordinate references, all256 distinct pair weights, off-diagonal-only localization, on-axis symmetry, unnormalized save/reload and reproducible metadata. New UI cases cover defaults/explicit water selection, current metadata geometry/all-pair default grid, main dataset revision staleness without recomputing, every reconstruction parameter's stale state, offline saving and complete sidecar pitch/nonzero timing. Existing interpolation endpoints/half-samples/window exclusion/invalid inputs/legacy assumptions/worker cancellation/close/signed-display immutability cases still pass; colorbar identity is additionally retained across display changes.
- -m py_compile oempa/tfm.py ui/tfm_workspace.py ui/workspace.py tests/test_tfm_offline.py tests/test_ui_tfm_offline.py tests/test_ui_phase3.py tools/validate_tfm_production_offline.py: passed. Fresh oempa.tfm/ui.tfm_workspace imports load neither oempa.api nor oempa.driver; seven-file compile/whitespace checks passed.
- Desktop tools/validate_tfm_production_offline.py: passed, fake backend installed before GUI import, device operations forbidden. Nine real-window cases at1300x820/1100x700 cover no-source block, current/offline metadata input, scrolled settings, normalized/dB plots, parameter/new-FMC staleness, no tab/display recomputation, numeric save/reload and cooperative close during a controlled cancellable reconstruction. No layout issues, traceback or layout warning; clean_close=true,sdk_loaded=false,raw_unchanged=true. Minimum-size canvas212px (197px with longer stale status) and usable diagnostics; screenshots visually reviewed. Established desktop execution bypassed sandbox Tcl initialization issue without environment changes.
- Synthetic signed-int8 current/offline16x16x3001 reconstruction localized the specified (1.0,12.0)mm point exactly on the201x231 grid. Latest default-grid core times0.230s(current) and0.404s(offline), observed while regression tests also ran; earlier isolated observations0.23-0.28s. These are single-machine observations, not guarantees. Source arrays are byte-identical after reconstruction/display/save/reload; current/offline results numerically equal. An initial validation-fixture sidecar lacked required common fields and correctly loaded as metadata-incomplete; only the synthetic fixture was corrected, production metadata validation was not weakened.

Limitations: homogeneous isotropic single-velocity straight-line point-element linear array only, equal pair weights, no wedge/refraction/Snell/multilayer/anisotropy/curvature, automatic material/velocity inference, system-delay correction, physical calibration, apodization or Hilbert envelope. Source signed callback MAX data is not guaranteed untouched pre-compression RF; quantitative/coherence/phase fidelity and physical wiring remain unverified. Default water region can extend beyond captured time support; those paths contribute zero rather than extending data or adding hidden correction. No agent-run reconstruction of a newly acquired real dataset or acoustic/defect identification is claimed; real-Tk validation used labeled synthetic fixtures only. STOP after offline completion; no connection/application/acquisition authorized by this task.

### Offline FMC/B-scan inspection completed - 2026-10-13

Active checkpoint: authorized cached-data display improvements implemented/validated; STOP offline. Read AGENTS.md completely and inspected repository GUI/workspace/BScanProcessor and safe test patterns before changes. No OEM-PA handle/connection/read/write/acquisition, native build, configuration/network change or new hardware dataset. No peak is identified as a reflector, echo or defect. Existing FMC configuration, Stage3C mixed-source verification and immutable first-frame acceptance are untouched; A-scan/PA acquisition and plotting behavior remains intact.

FMC tab now offers Trace view: Individual TX/RX (default, unchanged signed trace/selection) or All diagonal traces. The latter plots every FMC[e,e,:] together with a compact logical TX/RX legend, captured metadata time axis (or sample indices for legacy cubes), stale indication and dataset provenance. Diagonal scale choices None/Global/Per trace affect copied display arrays only. Existing individual TX/RX controls remain available; changing any of these views submits no controller/backend operation. Full metadata/probe mapping is retained unchanged, with no physical channel-mapping inference.

B-scan remains the existing FMC pulse-echo diagonal, not mechanically scanned. RF/Absolute remain; new normalization None/Global/Per trace and contrast Linear/Boost weak (sqrt) are explicitly labeled display processing only. Global divides all displayed samples by a common absolute peak and preserves channel ratios. Per trace divides each diagonal by its own displayed peak, with zero traces left zero; the UI states this removes channel amplitude ratios. Normalization uses samples within the software gate, so changing the gate can change the display scale. Square-root contrast applies sign(x)*sqrt(abs(x)/display_limit)*display_limit, boosting relative weak magnitudes without changing RF sign. Absolute converts to float before abs, safely handling int8 -128. No gain/filter/time/format setting, raw array, diagonal extraction array, metadata, acquisition readiness/revision or dataset freshness is changed by display processing. No processing options are written into acquisition sidecars or saved raw data. All-zero displays have finite fallback limits. Legacy timing stays unknown, uses sample indices/full-record normalization and ignores time gates rather than inventing units. Finite ordered gates required; a single-sample gate gets half-sample image edges rather than degenerate extent.

Pure ui/fmc_inspection.py contains display-only copied float64/read-only arrays and no device/Tk imports. GUI uses existing BScanProcessor output and current cube; no acquisition/configuration/control API added. Compact B-scan source label points to full recorded timing/provenance in FMC tab, preserving plot space. Initial real-window validation found clipped diagonal legend/y-label and a tight-layout warning on the cramped B-scan. Compacted display labels/title/legend and redundant summary placement; final validation has no warning/traceback/clipping. This is a display-layout adjustment only.

Files created: ui/fmc_inspection.py; tests/test_ui_fmc_inspection.py. Modified: gui.py (display variables/rendering/presentation only), ui/workspace.py, tests/test_ui_phase3.py, tools/validate_gui_usability_offline.py (synthetic diagonal/contrast checks and separate output directory), AGENTS.md. Screenshots/validation.json generated in artifacts/fmc_inspection_offline; previous review artifacts preserved. No oempa module, bridge/API/DLL, controller/state, verified configuration, backup_original.txt or historical dataset changed. fmc16_full.txt SHA256 rechecked unchanged:0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7.

Final validation using <python>:
- -m unittest discover -s tests -p 'test_ui_*.py' -q:213 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q:20 passed. Total233, preserving220 baseline plus13 new cases. Only previously inspected offline/pure/fake/native-synthetic patterns ran; unrestricted discovery and hardware-capable diagnostics were excluded.
- New cases cover raw/no normalization, signed-minimum absolute safety, global amplitude ratios, per-trace/zero channels, square-root visibility/sign, gate-only scaling, source-byte immutability across every option, finite all-zero output and invalid inputs. GUI cases cover16 diagonal traces/labels/timing and return to individual TX/RX, RF/Absolute normalization/contrast/gates, legacy sample-index views, single-sample/invalid gates. Controller submit is asserted never called; cube/diagonal bytes, metadata identity and full application state are preserved. Existing A-scan, PA, FMC verification/acceptance/persistence regressions continue passing.
- -m py_compile gui.py ui/workspace.py ui/fmc_inspection.py tests/test_ui_fmc_inspection.py tests/test_ui_phase3.py tools/validate_gui_usability_offline.py: passed. Pure display import asserted no oempa.api/driver loaded; whitespace checks passed.
- Desktop tools/validate_gui_usability_offline.py: passed18 layouts at1300x820/1100x700, including synthetic all16-diagonal/normalized contrast views. Fake backend is installed before GUI import and forbids connect/apply/acquire; hardware_imported=false, clean_close=true, errors/layout issues empty. Minimum-size diagonal/B-scan screenshots visually reviewed. Sandbox Tcl limitation handled by existing approved desktop execution, with no environment changes.

STOP after offline inspection-tool validation. No physical interpretation or new hardware experiment authorized/performed; normalization/contrast changes remain visibly display-only.

### FMC immutable first-frame acceptance completed - 2026-10-09

Active checkpoint: offline implementation/validation complete. STOP before manual hardware review/testing. User explicitly approved the narrowly scoped first-frame policy after reporting a complete256/256 ordered first sequence followed by25 duplicate-ID callbacks, unexpected/malformed0. This is user-reported manual evidence; no new hardware experiment was performed in this task. Physical firing count remains unknown. This supersedes the former rejection of post-frame duplicates only; no generic ignore-duplicates policy was introduced.

Full16x16 production FMC arms an SDK-free local native gate only after OFF preparation and256-cycle preallocation, alongside the existing512 callback/64 marker chronology. Each first-frame callback must be the next exact cycle0..255 with matching point count,1-byte Signed8-bit encoding and valid MAX pointer/header/storage capacity. Duplicate, missing/timeout, unexpected, malformed or out-of-order pre-completion records reject. The gate remains failed after its first error. After cycle255, callback-owned sample/header storage is immutable: later callbacks update chronology/aggregate/post-frame counters only and return before copying. Completion becomes visible to the worker only after the final copy releases the same storage mutex. No SDK/device/Tk/file I/O or resizing added to the callback. Existing normal/single-element A-scan callbacks remain outside the gate. OFF preparation resets the gate and chronology for a subsequent independently user-started attempt.

Local condition-variable notification wakes the worker on completion/error; the callback does not request OFF. The worker uses the existing acquisition.stop/finally OFF path, validates frozen first-frame evidence after shutdown, then copies/processes/publishes the candidate. OFF failure, cancellation or other existing safety failures cannot publish accepted data. No automatic retry. State/controller queue semantics unchanged: Current is established only by successful worker completion, never by callback completion alone. New additive bridge exports Begin/Get/WaitFMCFirstFrame manipulate local storage only; no new AOS API call or SDK semantics assumed.

Post-frame callbacks cannot enlarge/overwrite/reject a valid first frame. They remain visible separately, including unexpected/malformed post counts and chronological first post arrival. Raw remains256xN; FMC16x16xN; cycle=tx*16+rx. B-scan remains existing software-only FMC diagonal. GUI logs actual accepted count, post-frame count, post-frame invalid counters and cube shape with bounded rejection reasons. Metadata has optional immutable frame_evidence: expected/accepted256, ordered complete boundary, missing[], pre-error counters0, post counters, total arrivals, boundary/first-post positions, bounded chronology/lifecycle events and overflow status. Existing acquisition_acceptance, captured timing, config identity/hash/revision, mixed-source verification and probe provenance persist unchanged. Old sidecars without frame_evidence remain compatible. Post-frame chronology overflow is reported; it does not invalidate a frame whose complete first256 chronological rows and native immutable boundary remain proven. Missing first-frame chronology proof still rejects.

Legacy require_records remains an aggregate-only diagnostic helper for compatible offline tests; neither production acquisition nor acceptance runner uses it to decide first-frame acceptance. Its counter-only regression was renamed to clarify that aggregate counts cannot prove immutable samples. Production failure artifact retains native frame/order/stats; if instrumentation itself fails, the original error is preserved alongside diagnostic failure, without fabricating acceptance.

Created: bridge/fmc_first_frame.h; tests/fmc_first_frame_native.cpp; tests/build_fmc_first_frame_test.cmd; tests/test_ui_fmc_first_frame.py. Modified: bridge/oempa_bridge.cpp/.h and rebuilt DLL/build outputs; oempa/api.py, acquisition.py, gui_backend.py, fmc_acceptance.py, dataset.py; gui.py (diagnostic messages only); tools/validate_phase5_stage3_acquisition.py (source only, not executed), validate_gui_usability_offline.py (separate review output); tests/test_ui_backend_offline.py, test_ui_native_wrapper_offline.py, test_ui_stage3d_offline.py, test_ui_phase3.py; AGENTS.md. SDK-free harness executable/build outputs and artifacts/fmc_first_frame_gui_offline were generated. No protected configuration, historical acquired dataset, configuration generation, Stage3C provenance exceptions, probe mapping, PA or network behavior changed. fmc16_full.txt SHA256 remains0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7.

Validation commands/results:
- cmd /c bridge/build_bridge.cmd: passed; only existing C4005/C4091 vendor warnings. Build only, no device handle opened.
- cmd /c tests/build_fmc_first_frame_test.cmd: passed; SDK-free native harness.
- Python -m unittest discover -s tests -p 'test_ui_*.py' -q:200 passed.
- Python -m unittest discover -s tests -p 'test_tfm_offline.py' -q:20 passed. Total220, preserving201 baseline with19 added cases; obsolete aggregate-counter test is explicitly diagnostic-only. Hardware-capable general test discovery was not run.
- New regressions cover ordered256,25/26 post callbacks, early duplicate/missing/out-of-order/unexpected/malformed/wrong count/size/sign/bit size, byte immutability through post callbacks, post invalid counters/overflow, numerical save/reload and sidecar evidence, allTX/RX/diagonal selection, fake-ctypes exports/error handling, worker wake-up, OFF failure before copy, production backend and GUI accepted post-frame reporting. Existing single-element A-scan/FMC mixed-source cases pass unchanged.
- Python -m py_compile changed Python sources/tests: passed. Pure imports oempa.fmc_acceptance/oempa.dataset passed without oempa.api or oempa.driver imported.
- Disconnected desktop tools/validate_gui_usability_offline.py: passed14 layouts at1300x820/1100x700, fake backend installed before GUI import, all hardware operations forbidden, hardware_imported=false, clean_close=true, no layout issues/tracebacks. Minimum-size synthetic FMC screenshot visually reviewed. Screenshots/validation.json in artifacts/fmc_first_frame_gui_offline. No Tcl/environment/software installation changes.

Remaining uncertainty: updated acceptance policy/notification/bridge has not been exercised against the OEM-PA here. Native harness uses synthetic7-point records to prove general N storage behavior; hardware3001-point acceptance awaits separate manual review/test. No hardware connection, application, acquisition, B-scan/TFM hardware acceptance or new dataset occurred. STOP offline.

### FMC production GUI/configuration preparation completed - 2026-10-09

Active checkpoint: offline implementation/validation complete; STOP before real hardware testing. No OEM-PA connection/access, hardware configuration application, acquisition, callback-storage operation, native build or network change occurred. Single-element A-scan generation/readback/acquisition flow remains unchanged. Exactly A-scan/FMC/Phased Array acquisition modes remain; B-scan/TFM remain processing/display tabs. Physical firing count remains unknown for historical hardware attempts. Strict Stage-3D duplicate rejection is unchanged; no post-frame/spillover acceptance or new retry authorized.

AOS mapping evidence inspected directly from installed PDFs using pdftotext -layout: Documents/7_Software_Functions_&_Parameter_List.pdf PDF page 20 (emission focusing Note 1) states each aperture bit corresponds to a probe element, 16-channel devices can use only the first 16 elements, and the first DWORD LSB is element 1. Reception focusing Note 1 repeats the convention. Documents/4_Software_API.pdf PDF page 134 FMC Example 1 describes software element 0 as the first probe element. Dedicated FMC examples are evidence for numbering only; that unsupported hardware API is never used here. Text extracts retained as artifacts/aos_parameter_list_offline.txt and artifacts/aos_software_api_offline.txt. MiKTeX reported inability to write its external log but produced the readable text extracts; no installation/environment repair was made.

The current software model therefore records logical 0-15 -> AOS probe elements 1-16, mapping_source=AOS SDK documentation, independently from physical_wiring_validation=Not independently tested. mapping_verified remains false (physical validation), without hiding the documentation-based mapping. Updated supplied full label: AOS F5-N32-P0.6mm 8062 C105 S2. Elements 32 and pitch 0.6 mm remain manual label-derived; F5/5 MHz remains inferred, not hardware discovered. Usable documented aperture count 16, span 9.0 mm at the supplied pitch. No access to elements 17-32, switching mechanism, electrical continuity, physical steering direction or geometry-dependent acoustic validation is claimed. New optional mapping/source/wiring/span metadata round-trips through the existing sidecar; old datasets retain their original unverified/unknown mapping rather than being retroactively upgraded. Manual description does not change hardware verification or automatically populate PA/TFM assumptions.

Inspection found normal GUI FMC Apply used the generic generated-file path, while the accepted Stage-3C path was an explicit unchanged-file entry point. Production mode=FMC/full16x16 Apply now routes to that existing hash-bound file path, with requested common Acquisition settings compared first to inspect_approved_fmc. Any changed common request is rejected before writing, never silently replaced by file defaults. Existing context-less/smaller backend interfaces remain compatible. Full256-cycle MultiHWChannel layout and cycle=tx*16+rx are unchanged. Exact path/hash/successful load/OFF/fresh verification requirements and the three approved SDK-unreadable categories remain intact; no broader provenance exception was added. Hardware critical fields must still match. FMC common-value edits requiring a new approved configuration remain a deliberate limitation; this task does not create a broader configuration-provenance policy.

FMC Mode Settings now shows logical TX/RX 0-15, counts16/16, combinations256, cycle mapping, documented probe mapping/wiring status and expected raw256xN/cube16x16xN. N is displayed from current verified FMC readback only, otherwise N/pending; no fixed3001 or100MHz UI assumption. Common editable Acquisition variables remain shared, with requested/actual distinction preserved. A-scan selectors/delays remain separate. Concise FMC logs include observed topology, apertures and captured timing without dumping256 cycles.

Production GUI previously lacked the strict counter guard installed by the Stage-3D acceptance runner. Extracted the identical require_records policy to pure oempa/fmc_acceptance.py and reused it in both paths. Optional generic acquisition hooks arm existing bounded native chronology after OFF preparation and validate local counters during polling and after finally-stop, before copying/accepting data. Default/single-element behavior unchanged. Full16x16 production FMC now rejects duplicates (including post-completion duplicates), malformed/unexpected/missing records and bad totals; no candidate can be accepted merely because all unique IDs appeared. Failure summary distinguishes a chronologically proved complete first sequence from later invalid/additional callbacks without accepting them. Backend last_fmc_diagnostic retains full bounded native order/statistics/reason; native callback/storage implementation unchanged. Runner avoids arming twice now that the production backend arms chronology. Hooks perform local diagnostic reads on worker threads; callback still performs no device access/file I/O and no active storage resize. First-occurrence chronology remains immutable; sample slots retain the historical overwrite behavior, which is safe only with strict rejection and must not be used to recover a rejected dataset.

Accepted future FMC metadata records configuration verification (including mixed sources) and strict acceptance explicitly, in addition to existing snapshot/provenance/file hash/requested pulse/gain/filter/timing/encoding/cycle mapping. Generic capture_metadata does not independently assert strict FMC acceptance; only the guarded production result attaches that status. Rejected callbacks produce no accepted cube or metadata. Probe provenance captures the manual label/documented mapping and separate untested wiring.

FMC display uses metadata-derived time, title FMC A-scan - TX n / RX n, Signed amplitude, ASCII us and selected TX/RX summary. Selection is display-only. Open FMC (offline) uses the serialized loading worker and existing FMCData.load/sidecar architecture; full16x16 integer cubes are required, metadata is retained, legacy data uses sample indices and loaded data remains explicitly historical/stale even if its original revision is unknown. Loading never establishes hardware verification/readiness. Existing diagonal BScanProcessor is reused unchanged: B[e,:]=FMC[e,e,:], shape16xN, RF/Absolute/software gates, logical-channel horizontal axis and captured time vertical axis. No time-to-depth conversion or extra hardware action. No waveform feature interpreted physically.

Real-window fixes: compact Probe form and FMC summary fit at minimum size; redundant FMC mode-help text hidden because summary includes its architecture. Initial vertical divider now waits for a realized usable height, fixing an observed startup race that collapsed the workspace. Offline validation tool now checks workspace visibility/panel proportions and renders synthetic FMC/B-scan with 751 samples,25MHz,2us start at both sizes. Final fourteen layout observations at1300x820/1100x700 passed, no traceback/clipping, disabled disconnected Acquire, no API/driver import, clean cooperative close. App-only screenshots and validation.json: artifacts/fmc_gui_offline. Synthetic views are clearly historical fixtures, not hardware datasets. Screen capture keeps the test window on top temporarily to avoid occlusion/PrintWindow TkAgg artifacts; final screenshots visually reviewed.

Files created: oempa/fmc_acceptance.py; documentation text extracts and artifacts/fmc_gui_offline review files. Files modified: gui.py; oempa/probe.py; oempa/dataset.py; oempa/gui_backend.py; oempa/acquisition.py (optional hooks only); ui/state.py (unknown-revision historical dataset label); ui/setup_panel.py; ui/workspace.py; ui/presentation.py; ui/layout.py; tools/validate_phase5_stage3_acquisition.py; tools/validate_gui_usability_offline.py; tests/test_ui_backend_offline.py; tests/test_ui_phase3.py; tests/test_ui_usability.py; tests/test_ui_stage3d_offline.py; AGENTS.md. No bridge/API/driver/native/config-builder/verification implementation, protected configuration or historical acquired data edited. FMC file SHA256 remains 0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7.

Final commands with <python>:
- -m unittest discover -s tests -p 'test_ui_*.py' -q: 181 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q: 20 passed.
- Total201: all192 baseline cases plus9 new focused cases (FMC approved-path routing/common mismatch before write, strict poll/shutdown rejection before copy, documented mapping/wiring, TX/RX/diagonal dynamic-N display with zero submitted hardware operations, historical load, mapping sidecar round-trip and complete-first-sequence strict rejection summary). Existing A-scan/ASCII/mixed-source/chronology/state/cancellation regressions remain passing. Only inspected offline patterns ran; hardware-capable general test discovery and acquisition runner were not executed.
- -m py_compile for all17 modified/new Python modules/tests/tools: passed. Pure oempa.fmc_acceptance/probe/dataset/ui.presentation imports passed without device modules.
- tools/validate_gui_usability_offline.py: desktop offline stub, exit0; no hardware import/access and clean_close true. Existing sandbox Tcl issue unchanged; no machine-specific application workaround.

Final admission also rechecks complete local counters/chronology after array processing and metadata construction, before publishing the result; diagnostics overflow blocks acceptance. Final evidence stays in backend last_fmc_diagnostic. No SDK callback-drain guarantee is inferred from OFF returning. Offline181 UI tests and backend syntax check passed again after this final check.

Unresolved before hardware testing: strict policy intentionally rejects later duplicate callbacks even when a first complete ordered frame is proved. Acceptance-policy review and any new acquisition require separate explicit authorization; no retry or B-scan/TFM hardware acceptance is implied by this GUI readiness task. Complete vendor warning-stream capture and physical wiring/acoustic validation remain deferred. STOP after offline validation.

### Production GUI organization/usability completed - 2026-10-09

Active checkpoint: offline implementation and validation complete. STOP. No real OEM-PA access, connection, configuration write, acquisition, callback-storage operation, native build or network change occurred. User reports successful manual single-element A-scan testing; this task did not independently reproduce that physical experiment or interpret waveform features. Hardware configuration generation, fresh readback verification, FMC mixed-source exceptions/strict duplicate rejection, PA acquisition block, cancellation, callback safety and stale-data rules are preserved.

Device remains the existing fixed endpoint/connection/readback panel. Probe now contains editable manual label fields initialized from the supplied AOS F5-N32-P0.6mm 8062 C105 1-32 marking. Label provenance is user_supplied_label; interpretation of F5 as 5 MHz is inferred_unverified. Later edits are user_entered. Identity and physical mapping remain unverified; logical_to_physical remains None. Manual probe count 32 is explicitly separate from OEM-PA capability 16 logical channels; no physical subset is assumed. Probe description edits affect metadata only, not hardware readiness/config revision or PA/TFM geometry assumptions. An immutable description captured on the main thread is passed to future A-scan/FMC dataset metadata and survives JSON sidecar round-trip; old sidecars lacking this optional field remain readable.

Acquisition holds single instances of common Pulser, Receiver, Acquisition Window and Advanced TimeSlot controls, with distinct actual Hardware Readback showing captured timing/sampling/count/encoding/compression. Start is editable for A-scan; FMC/PA retains its existing configuration-defined start behavior. The form scrolls vertically so all controls/readback remain reachable at minimum size. Mode Settings contains exactly A-scan/FMC/Phased Array: A-scan logical TX/RX 0-15 plus Advanced delays; FMC retains 16x16 grouping/mapping; PA aperture/geometry/offline focal-law controls moved here from the display tab. No config algorithms changed. PA action label is Acquire PA and remains disabled by the existing safety gate. Display tabs remain A-scan/FMC/B-scan/Phased Array/TFM. ASCII us and clean signed A-scan title/axes/three-line summary are preserved.

Persistent diagnostics uses a vertical draggable divider, approximately 26% of usable height by default (panel 187 pixels at 1300x820, 157 at 1100x700), wrapped selectable/copyable Text and vertical scrollbar. Auto-follow runs only when already at the bottom. Visible output is bounded to 1000 lines and 4000 characters per message; separate chronological history retains full messages up to 2000 records with monotonic message numbering. Clear Log clears only the visible view, leaving history, original verification reports/artifacts, hardware state/provenance and datasets intact. Top line is concise Device / Mode / Operation / Config / Data. Worker-to-Tk queue/controller semantics unchanged.

Files created: oempa/probe.py; ui/diagnostics.py; tests/test_ui_usability.py; tools/validate_gui_usability_offline.py. Files modified: gui.py; oempa/dataset.py; oempa/gui_backend.py (optional probe metadata propagation only); ui/setup_panel.py; ui/layout.py; ui/workspace.py; ui/presentation.py; tests/test_ui_phase3.py; tests/test_ui_gui_offline.py; AGENTS.md. Real-window screenshots and validation.json are in artifacts/gui_usability_offline. No protected configuration or historical dataset modified; fmc16_full.txt SHA256 remains 0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7.

Commands run with <python>:
- -m unittest discover -s tests -p 'test_ui_*.py' -q: 172 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q: 20 passed.
- Total 192 passed: all 185 baseline cases plus seven regressions covering probe edit/state/provenance round-trip, common controls/mode switching, requested-vs-actual readback, Clear Log safety, scroll-follow and bounded diagnostics. Existing ASCII, A-scan routing/verification and FMC provenance/acceptance tests remain passing. Only inspected offline patterns were run; hardware-capable general discovery was not run.
- -m py_compile gui.py ui/setup_panel.py ui/layout.py ui/workspace.py ui/presentation.py ui/diagnostics.py oempa/probe.py oempa/dataset.py oempa/gui_backend.py tests/test_ui_phase3.py tests/test_ui_usability.py tests/test_ui_gui_offline.py tools/validate_gui_usability_offline.py: passed.
- Pure imports oempa.probe/oempa.dataset/ui.diagnostics: passed without oempa.api or oempa.driver imported.
- tools/validate_gui_usability_offline.py: passed on real desktop Tk with a backend stub installed before GUI import that forbids connect/apply/acquire. Ten layouts checked across 1300x820 and 1100x700, including FMC/PA mode controls; no traceback or detected clipping, Acquire disabled, no device modules imported, cooperative disconnected close complete. Initial check found Acquisition clipping, fixed with the scrollable form; final screenshots confirm usable Probe/PA layouts. Restricted sandbox Tk still has the documented init.tcl initialization issue; established desktop runtime worked without environment repair or application Tcl-path workaround.

STOP after offline validation. No further hardware attempt or imaging acceptance was performed or authorized here.

### Mode Settings presentation cleanup completed - 2026-10-09

Active checkpoint: GUI presentation/layout only; offline validation complete. STOP. No device access/connection, configuration application, acquisition, native build or network change occurred. A-scan configuration generation, verification, acquisition, TX/RX meaning, FMC provenance/strict acceptance, PA calculations and callbacks remain unchanged. Probe metadata feature expansion is deferred; existing Probe tab remains intact.

Mode Settings now has an Acquisition Mode group with Mode dropdown. A-scan has separate Channels and Timing groups: Transmit (TX) / Receive (RX) readonly dropdowns enumerate logical OEM-PA channels 0-15, with Physical probe mapping: Unverified; Start / TX Delay / RX Delay entries show separate ASCII us units. Quantization steps are removed from the primary form but existing backend validation is untouched. Channel selectors are readonly while editable and disabled during owned operations; draft variables, mode routing, defaults and dirty/readiness semantics are preserved. FMC retains its logical channel-count controls. No display-tab change performs a hardware operation.

Production GUI unit labels/readback/plot/log presentation now uses ASCII us, including FMC/B-scan/PA/TFM views. Broken question-mark arrows/units in the manual A-scan UI are replaced. Title: Single-element A-scan - TX n / RX n; x-axis Time (us); y-axis Signed amplitude. Signed samples and metadata-derived time axis remain identical. A-scan summary is three compact lines: logical TX/RX, pulse width and analog/digital gain; captured start/range/sampling/sample count; Physical mapping: Unverified. Dataset revision, delays and callback-buffer source remain available in lower logs and unchanged stored metadata. Completion log remains A-scan acquisition complete. ASCII normalization of incoming status/log unit text affects rendered strings only, never original state/metadata. Other problematic GUI separators use ASCII equivalents; PA degree label uses deg with no calculation change. Apply Configuration / Acquire A-scan / Stop / Save data commands and backend semantics are unchanged.

Files modified: gui.py; ui/setup_panel.py; ui/presentation.py; ui/workspace.py; ui/tfm_workspace.py; tests/test_ui_phase3.py; AGENTS.md. No files created. No oempa module, driver/API/native bridge, verified config/backup_original, saved dataset or network setting edited.

Offline GUI tests add two focused cases for grouped layout, logical selectors, readonly/disabled restoration, ASCII visible unit labels and display-only status normalization. Existing synthetic A-scan plot/save test is strengthened for exact title/axes, three-line summary, original metadata object identity, signed samples and persisted metadata integrity. Existing PA/TFM label assertions updated to ASCII presentation; all behavioral checks remain. Tests use fake Tk/backend and real Matplotlib, no real window or SDK/device invocation.

Exact commands with <python>:
- -m unittest discover -s tests -p 'test_ui_*.py' -q: 165 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q: 20 passed.
- Total 185 passed, preserving 183 baseline plus two new cases.
- -m py_compile gui.py ui/setup_panel.py ui/presentation.py ui/workspace.py ui/tfm_workspace.py tests/test_ui_phase3.py: passed.
Only inspected complete offline suite patterns ran; unrestricted discovery would include hardware-capable diagnostics and was not run. This is headless offline GUI validation, not real-window or hardware acceptance. STOP; no connection/acquisition or larger probe-metadata feature is authorized by this task.


### Single-element A-scan Apply routing regression fixed - 2026-10-09

Active checkpoint: software-only bug fix completed. STOP. No OEM-PA connection/access, real hardware read/write, acquisition, callback-storage operation, configuration-file generation in configs, native build or network change occurred. No hardware retry is authorized. Complete offline regression is 183 passing (178 preserved plus five new cases).

Source trace: GUI _read_configuration previously chose config type from state.mode; only the ComboboxSelected event synchronized mode_var into state.mode. Setting/selecting the visible variable without that event left state FMC, built FMCConfig and dispatched backend.apply into its FMC branch. That branch loads the FMC file, obtains a fresh FMC-mode snapshot and verifies without approved-file provenance, reproducing the reported classification/start/TX-width/delay failure pattern. A-scan backend itself already cleared applied snapshot/request/FMC provenance, loaded its distinct normal configuration, forced OFF, refreshed status after load/reconnect and collected A-scan snapshot; no source evidence of readback-before-write or snapshot reuse in that branch was found. Snapshot mode is supplied by the requested backend branch, not inferred from actual hardware CycleCount. Reported hw_acquisition/no-provenance errors therefore identify FMC verification. No original manual-session log/selected-mode trace was provided, so the exact cause in that session (missed synchronization, viewing the A-scan display while acquisition mode remained FMC, old running process, etc.) cannot be independently proved. Do not claim the hardware write failed based only on those error strings.

Fix: mode_var now has a main-thread trace so selected acquisition mode automatically reaches state/config validation; Apply defensively resynchronizes selected mode before building/capturing its request. Removed reliance on combobox event binding. Backend generic Apply checks requested config type against controller context mode before any write; mismatched routing fails explicitly without selecting FMC as fallback. Direct existing-file PA/FMC workflows and matching legacy context-less backend calls remain compatible. Header shows Acquisition mode, and Mode Settings explicitly distinguishes acquisition mode from display tabs. Display-tab selection still does not reconfigure hardware or break FMC TX/RX waveform viewing.

A-scan uses fresh OFF post-load status. If observed CycleCount is not one or MultiChannel is not disabled, it builds a fresh A-scan topology-only failure snapshot and runs strict A-scan verification, without enumerating the old FMC table. No stale snapshot/provenance is reused and no FMC classifier/provenance exception is invoked. Failed topology cannot enable readiness; absent per-cycle data is not invented. With correct topology, all existing A-scan critical-field readbacks still run and must match. Same topology guard protects pre-acquisition revalidation. No hardware verifier rule, FMC approved hash/provenance whitelist, callback/SDK setter or acceptance semantics changed.

Error presentation: ConfigurationVerificationError now carries a concise mode/expected cycles/observed cycles/not accepted summary plus bounded first diagnostics; full report remains attached to queued exception/state. Main banner prioritizes the summary and is capped at 700 characters instead of joining every mismatch. Detailed readback logging emits at most 20 entries of 240 characters and an omitted-count notice; complete mismatch/evidence tuples stay available in state. Generic error banner/log text is also bounded. An unchanged 256-cycle result reports A-scan configuration verification failed / Expected cycles 1 / Observed cycles 256 / Configuration was not accepted, rather than hundreds of classification messages.

Five new offline regressions: GUI Apply from existing 256-cycle enabled FMC snapshot/provenance into fresh one-cycle disabled readback -> A-scan Verified; unchanged 256-cycle status -> bounded rejection with zero per-cycle getter calls; missed selected-mode event -> Apply resynchronizes and dispatches single-cycle config; request/controller mode mismatch -> no device/write call; 256 detailed errors -> bounded banner/log with full retained state. End-to-end tests use real GUI/controller/backend routing with fake Tk, fake API/device and mocked config saving. Fresh status is asserted to occur after simulated load, requested object is SingleElementAscanConfig with cycle_count 1, verifier snapshot mode is A-scan with no applied FMC provenance, old snapshot is not reused and FMC provenance is cleared. Existing normal/critical-missing A-scan and all FMC provenance/strict duplicate tests remain passing. Test harness aligns the class reference retained by its isolated fake GUI import; production config types are not weakened to duck typing.

Files modified: gui.py; oempa/gui_backend.py; ui/setup_panel.py; ui/presentation.py; tests/test_ui_phase3.py; tests/test_ui_single_ascan.py; AGENTS.md. No file created. driver.py/acquisition.py, native bridge/API, all verified configurations, backup_original.txt and saved datasets unchanged. FMC file SHA-256 independently reread offline and matches 0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7. No SDK behavior/signature changed; retained loader source shows OFF -> existing load -> reconnect/refresh before the added fresh readback.

Validation using <python>:
- -m unittest discover -s tests -p 'test_ui_*.py' -q: 163 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q: 20 passed.
- Total 183 passed, preserving 178 baseline plus five new cases.
- -m py_compile gui.py oempa/gui_backend.py ui/setup_panel.py ui/presentation.py tests/test_ui_single_ascan.py tests/test_ui_phase3.py: passed.
Only the inspected safe offline suite patterns ran; unrestricted discovery includes hardware-capable diagnostics and was not run. Hardware acceptance and real-window behavior for this correction remain untested; restart the production application to load updated code before a separately authorized manual test. STOP after offline fix/testing; no connection/configuration application/acquisition authorized by this task.


### Single-element A-scan GUI implementation completed ? 2026-10-09

Active checkpoint: user authorized software-only implementation of a manual single-element A-scan mode. Implementation and offline tests are complete; STOP. No OEM-PA connection, handle creation, hardware read/write, configuration application, acquisition, network change, native build or hardware-capable test occurred. No Stage-3D retry or B-scan/TFM hardware acceptance is authorized. Previous FMC failure evidence and strict duplicate rejection remain unchanged.

Created oempa/ascan_config.py with a frozen SingleElementAscanConfig and pure text builder. Defaults: TX/RX logical 0/0, pulse width 0.5 ?s, TX/RX delay 0/0 ?s, analog/digital gain 20/0 dB, start/range 0/30 ?s. Existing common controls retain TimeSlot 2000 ?s and filter 1. Generated normal-cycle configuration explicitly sets CycleCount=1, EnableMultiChannel=0, AscanBitSize=8Bits, Signed, automatic PointCount=0, Compression, one TX element and one RX element, one Standard static receive law, zero receive gain/TOF/wedge/center delays. No probe geometry, pitch, identity or physical mapping is assumed. Width/TX-delay 4-ns and RX-delay 5-ns steps are validated without silent rounding; nonfinite/invalid element/duration settings are rejected. Actual sampling/point count/factor come from readback, never new GUI constants.

Inspected installed AOS UTKernelDriverOEMPA.h emission/reception signatures and CustomizedDriverAPI.cpp parsing/write paths. Root EnableMultiChannel is an explicit saved parameter, necessary to disable a previously enabled FMC device. Root AscanBitSize is the documented 8Bits key. PointCount=0 selects existing automatic Compression SetAscanRange path; signed callback MAX values are displayed unchanged, not absolute/rectified in software and not claimed to be pre-compression RF. EnableFMC is deliberately omitted: vendor invokes the dedicated API only when its saved-parameter bit is present. Existing medium-level loader/reconnect/OFF path is retained, with no new device setter or ABI.

Backend dispatch adds normal A-scan apply/acquire while leaving FMC branches intact. A-scan writes only its separate future generated gui_ascan_config.txt, never verified configurations; tests use temporary directories. Application clears old applied truth before writing, forces OFF around the established loader, then requires strict hardware comparison of cycle count, disabled MultiChannel, logical TX/RX apertures, width, TX/RX delays, gains/beam/filter, start/range/TimeSlot, Signed/8-bit/Compression, positive consistent sampling/count/factor, Standard focus, DDF off and receive-law/wedge fields. Any unavailable required field or readable mismatch blocks. None of the three FMC SDK provenance exceptions applies to A-scan. Before a later manual acquisition, readback is repeated OFF and callback capacity is derived from actual point count; the existing single-cycle acquisition prepare/start/poll/finally-stop/cancellation path handles one callback slot. Local multi-A-scan storage naming does not enable hardware MultiHWChannel. Native callbacks/storage/control APIs were not changed; no device access or resizing was added inside callbacks.

GUI incrementally exposes A-scan TX/RX/start/delays in Mode Settings and uses existing Acquisition controls for width/gains/range/filter/TimeSlot. Buttons remain Apply Configuration / Acquire A-scan / Stop / Save data. A-scan support is added to supported state modes; PA remains blocked. Changing mode/settings dirties configuration and stales historical data; only connected/current/applied/readback-verified state enables acquisition. Controller workers still emit queued events, with all Tk/Matplotlib updates on the main thread. One-dimensional signed data has captured hardware timing in ?s and visible logical TX/RX, width/delays/gains/start/range/sampling/count/revision and Physical probe/channel mapping: Unverified. It is separate from an FMC cube and does not feed B-scan/TFM; obsolete FMC/B-scan plots clear when replaced by a manual trace. Existing .npy + hash-bound JSON sidecar persistence preserves requested settings separately from full hardware readback/field evidence. Offline reload is numerically equal and preserves metadata. Save dispatch supports either dataset; existing FMC interfaces/mapping/policy and PA gate remain intact.

Files created: oempa/ascan_config.py; tests/test_ui_single_ascan.py. Files modified: gui.py; ui/setup_panel.py; oempa/gui_backend.py; oempa/hardware_state.py; tests/test_ui_phase3.py; AGENTS.md. Existing unsupported-mode test now retains its PA assertion and permits the newly requested A-scan feature. Eleven added tests cover defaults/edit validation, explicit normal topology, strict missing/mismatch checks without provenance exceptions, state/dirty/stale gates, fake apply/failure/revalidation/capacity, nonzero-start 25-MHz metadata-derived plotting, signed samples and save/reload integrity. No bridge, acquisition.py, driver.py, FMC writer, verified configs, backup_original.txt, historical data, network or physical probe assumptions changed.

Exact safe validation using <python>:
- -m unittest discover -s tests -p 'test_ui_*.py' -q: 158 passed.
- -m unittest discover -s tests -p 'test_tfm_offline.py' -q: 20 passed.
- Total 178 passing; prior 167 baseline preserved plus 11 new cases.
- -m py_compile gui.py oempa/ascan_config.py oempa/gui_backend.py oempa/hardware_state.py ui/setup_panel.py tests/test_ui_single_ascan.py tests/test_ui_phase3.py: passed.

Only inspected offline patterns were run; general test discovery would include hardware-capable diagnostics and was not used. New backend tests replace the API before source import; GUI tests use fake Tk/adapter and real Matplotlib without loading SDK or opening a real window. Pure imports confirm no native device modules loaded. Hardware parser/application/readback/acquisition and real-window acceptance for this new mode remain untested and require separate authorization. Manual acquisition uses existing continuous-enable-until-stop semantics; neither one callback slot nor this UI implies exactly one physical firing. No waveform feature is interpreted physically. STOP after offline implementation.


### Stage 3D single retry completed — Case A chronology; strict acceptance REJECTED — 2026-10-09

User-authorized exactly one retry start has been consumed. Repeated OFF preflight passed; one production-GUI FMC start ran; strict duplicate rejection stopped it OFF. No dataset accepted/saved, no automatic retry, imaging acceptance or parameter compensation. STOP here. Physical firing count Unknown; probe/channel mapping Unverified. No further hardware action authorized.

Actual approved desktop command: specified Python tools/validate_phase5_stage3_acquisition.py --artifact-name phase5_stage3d_retry_20261009, exit1. UTC 20:13:05.763862..20:14:21.495699; enable request20:14:19.860291. Exactly one unchanged hash-matched fmc16_full.txt application through existing OFF/reconnect/AOS path; all load stages true, parsed256. Initial connection observed previous CycleCount1/MultiChannel supported-disabled; after application/readback CycleCount256, MultiChannel supported-enabled, gains20/0/beam0, Start0us/Range30us, TimeSlot2000us, PointCount3001, sampling100MHz, PointFactor256, Compression/Signed/8-bit enums0, filter1 and logical TX/RX mapping match. No readable mismatch/read error or observed SDK modal warning. Revision9 reached Verified(mixed sources)/FMC-ready; production worker repeated OFF verification before start. Exactly288 approved applied-configuration fields remain distinct with actualNone (classification, base TX width/delay); no new exception. OFF preparation twice used256x3001 bytes; chronology armed once after final preparation. No callback device API or active storage resize.

**Case A PROVED for this retry:** 1-based arrivals1..256 were exactly cycles0..255; arrivals257..282 were exactly cycles0..25. First duplicate cycle0 at arrival257/event261; all256unique present at arrival256/event259 (marker260). Every cycle c first occurs at arrival c+1; event indices cycle0=2, cycle1=4, cycles2..255=c+4. Complete first-occurrence arrays/chronology preserved. No pre-completion duplicate. This proves callback order for this retry only, not historical284-run order or physical pulse count.

Final:282callbacks,256/256unique,26duplicates IDs0..25, missing=[], unexpected=0, malformed=0. All282logged headers3001points/1byte/signedtrue/bitSize0. No overflow:282/512callbackslots+16/64markers,298events. ON requestevent1, firstcallbackevent2 (marker3), ON successfulreturn5. First OFF request272, entered273, lastcallback arrival282/cycle25/event289, successfulOFFreturn290. Final observations291 and298 both lastarrival282. 266callbacks before OFF request (first256+duplicates0..9);16callbacks IDs10..25 between OFF entry/return; none observed after first OFF return through final snapshot. Native markers represent mutex-serialized observations and native request boundaries, not independent physical OFF timing/drain guarantees.

Last successful poll250unique at20:14:20.430000; next guard found duplicates0..9 with no missing and raised before returning a complete count. Existing finally-stop ran immediately; remaining callbacks logged during native OFF call. Strict rejection unchanged despite Case A. No accepted NumPy raw matrix/FMC cube, metadata, save/reload or selector/display acceptance. First-occurrence diagnostic evidence is immutable but per-cycle sample storage still overwrites repeats; do not save/recover first-sequence data from overwritten slots.

Cleanup succeeded: three post-enable OFF returns/events290,294,297, clean disconnect/handle-storage release/window close. clean_close/acquisition_off_at_close/protected_files_unchanged alltrue. All pre-existing configs/data hashes preserved; no forbidden APIs/network/probe/gain/TimeSlot/pulse/filter change. GUI progress17events2..250 thenerror;559acquisition-operation ticks max0.0798357s;1209total ticks max0.5000273s including initial schedule. Device left approved FMC/OFF with no restoration write. No hardware call after this completed attempt.

After attempt: offline UI pattern147passed; separate TFM20passed, total167preserves baseline. Runner syntaxcheckpassed. Only pre-execution codechange labels hypothetical accepted retry filename fmc_stage3d_retry_acceptance_<UTC>.npy; no such dataset created. Files modified tools/validate_phase5_stage3_acquisition.py and AGENTS.md; new artifacts/phase5_stage3d_retry_20261009 contains validation.json, chronology.json, result.md and four preflight screenshots. Prior artifacts untouched. Full report/result.md includes exact chronology/first-occurrence mapping/constraints. STOP after this single retry; global acceptance unchanged and no B-scan/TFM acceptance begun.

### Stage 3D retry explicitly authorized; pre-execution checkpoint — 2026-10-09

User explicitly approved exactly ONE acquisition start after unchanged-file OFF application, full strict Stage-3C verification and preallocation. Read entire AGENTS.md and inspected current guarded runner, backend refresh/verification/preallocation, callback chronology and unchanged SDK LockDevice/UnlockDevice contracts. Prior software-only STOP superseded only for this single authorized attempt; no automatic second start, acceptance relaxation, parameter change or B-scan/TFM acceptance. Fresh artifact directory selected: artifacts/phase5_stage3d_retry_20261009. Existing report absent; approved file hash matches 0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7. Runner still rejects all duplicates and preserves local diagnostics through OFF/disconnect/destruction. A minimal persistence filename change labels any strictly accepted output fmc_stage3d_retry_acceptance_<UTC>.npy; no hardware/acquisition behavior change. Hardware execution pending; no result presumed. Next action: run the guarded production GUI tool once with --artifact-name phase5_stage3d_retry_20261009 using specified Python and established desktop runtime. Stop after the attempt regardless of outcome.

### Stage 3D retry instrumentation ready; software-only STOP — 2026-10-09

The user authorized bounded chronological instrumentation and offline tests only. No OEM-PA connection/access, acquisition, configuration write, network change or retry occurred. Prior hardware authorization remains exhausted. Current strict acceptance is unchanged: duplicates still reject, no spillover exception, partial/ambiguous data not accepted/saved. Previous Stage-3D arrival order remains unproven.

Added fixed native CallbackOrder storage: 512 callback events plus 64 reserved lifecycle events, no wrapping/overwrite, explicit dropped counts, immutable first-occurrence indices and first duplicate/unique-ID/last-callback boundaries. All observations share the callback mutex and monotonic event counter; arrival_index separately counts callbacks. Each arrival records cycle/sample count/size/sign/bit size and malformed/unexpected/duplicate bits. Null headers and representation mismatches are visible. The callback performs no device API access, file I/O, allocation or diagnostic storage resize. Existing sample copying/per-cycle overwrites and strict rejection are preserved; first-occurrence diagnostic evidence never overwrites.

Lifecycle markers: native ON request/return, first callback, all required unique IDs observed (not proof of validity/acceptance), first duplicate, native OFF request/entry/return, final callback observed at snapshot. Request markers describe native function boundaries, not earlier worker decisions; SDK bool return status is separate. A callback can precede ON-return. Final snapshot records last seen callback, not SDK drainage. Event ordering is mutex-serialized native observation order; no physical firing-count claim or independent hardware timing. Overflow makes ordering incomplete and prevents successful acceptance-runner completion; first-event indices remain retained even after event overflow.

Added local-only Begin/Get exports and fixed int64 ctypes decoding. Begin arms once per handle after OFF preparation with empty counters; production runner invokes it just before its one enable. No extra SDK calls introduced. Runner persists callback_order after acquisition finally-stop and refreshes after OFF/disconnect before destroying handle; final snapshot errors cannot prevent destruction. Fresh --artifact-name phase5_stage3d_retry_<label> supports a future separately authorized attempt, preserving original artifacts and refusing an existing validation.json. Default still refuses the original recorded run. No runner execution occurred now.

Files created: bridge/callback_order.h, oempa/callback_order.py, tests/callback_order_native.cpp, tests/build_callback_order_test.cmd, tests/test_ui_callback_order_offline.py, artifacts/phase5_stage3d_retry_instrumentation/README.md and four synthetic JSON logs. Modified: bridge/oempa_bridge.h/.cpp, oempa/api.py, tools/validate_phase5_stage3_acquisition.py, tests/test_ui_native_wrapper_offline.py, AGENTS.md. Bridge DLL/OBJ/LIB/EXP and SDK-free test EXE/OBJ rebuilt. GUI/controller/acquisition.py/verifier/configuration writer, protected configurations/backup_original and actual saved data unchanged. FMC file SHA-256 still 0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7; historical FMC SHA-256 still ad7db22cd9532ded625f8ae401d7cf72d8a715327c42f6fb1cd28b57841bf4fe.

Offline validation: cmd /c tests\build_callback_order_test.cmd -> exit 0, harness has no SDK linkage; cmd /c bridge\build_bridge.cmd -> exit 0 with existing C4005/C4091 warnings only. Specified Python -m unittest discover -s tests -p 'test_ui_*.py' -q ->147 passed; separate -p 'test_tfm_offline.py' -q ->20 passed. **167 total preserves 160 baseline plus seven new cases.** Five-file py_compile passed; pure decoder loads no device API. No general discovery/hardware-capable test ran. Tests exercise exact late versus early duplicate order, first occurrences, lifecycle/JSON artifact persistence, bounded callback/marker loss, malformed representation and fake-DLL ABI/error handling. Synthetic late 284-arrival log has unique completion event259 before duplicate263; early257-arrival log has duplicate16 before completion261. Neither is a hardware observation or accepted dataset.

STOP with instrumentation ready. Do not connect/reapply/acquire automatically. Future Stage-3D retry requires explicit authorization and unchanged strict OFF preflight; no shutdown-spillover acceptance is authorized.

Repeated request revalidation on 2026-10-09: reread this latest checkpoint; reran only the same safe offline discovery patterns, 147 UI/native-synthetic/fake tests plus 20 TFM tests, all 167 passed. No implementation changes, device access or hardware-capable tool execution. Instrumentation remains ready; STOP before retry.

### Stage 3D callback-order/source diagnostic completed — 2026-10-08

Active checkpoint: software/source diagnostic ONLY. No hardware call, connection, configuration application/write, acquisition, callback-storage change, native build or retry occurred. Read this file completely and inspected original artifacts/phase5_stage3d/validation.json, runner, native callback/counters/storage, acquisition polling/stop and installed AOS example/headers. STOP before any Stage-3D retry. Earlier single-acquisition authorization is exhausted.

Conclusion: **first sequence exactly 0..255 followed by spillover 0..27 remains UNPROVEN.** Saved evidence contains aggregate cycle counters and unique-count polls, not chronological arrival order, callback indices/timestamps or stream frame/sequence identity. Existing per-cycle storage overwrites repeats. Both synthetic orders 0..255,0..27 and 0..251,0,252..255,1..27 fit final counts, successful polls, and the rejecting aggregate snapshot (all IDs present, duplicated 0..11). The latter duplicates before completion. Therefore A versus B cannot be resolved; contiguous duplicate IDs do not justify B. No accepted dataset recovered/saved.

Observed API chronology: last successful poll 252 unique at 20:30:09.654058 UTC; rejecting poll at zero-based API index 1376, local statistics 1377; first successful OFF invocation 1378; final statistics 1379 report total 284/duplicates 28. Total 284 is a final post-stop observation, not a timestamped proof every callback arrived before OFF. Sixteen additional counter increments occurred between rejecting/final snapshots; relation to effective hardware OFF unknown. First callback, first occurrence per cycle, first duplicate, exact complete boundary and final callback times/IDs cannot be recovered. last_off_utc 20:30:09.938022 is later cleanup, not initial OFF-request timestamp.

Vendor evidence: UTKernelDriver.h:613–623 defines eAcqOn as enable shot pulse and eAcqOff as disable, bool as communication success, without callback-drain guarantee. OEMPAApplicationExampleDlg.cpp:520–539 toggles acquisition with checkbox; callback :702–717 accumulates bytes/frame IDs and timer :775–794 computes ongoing throughput/frame rate, supporting continuous enabled acquisition rather than one-table contract. AcquisitionFifo.h describes driver-thread FIFO input, multiple sequences and access contention. UTBasicEnum.h describes internal/external sequence triggering. No inspected API/source establishes synchronous callback drainage on OFF, precise OFF latency, active Stage-3D trigger mode or ascending arrival order. These sources support B as plausible but do not prove B for this run.

Stopping explanation: native count counts received slots (unique cycles); acquisition.acquire polls at default 20-ms waits plus processing/scheduling, breaks immediately on returned complete count and stops in finally. Runner checks statistics/headers inside get-count wrapper BEFORE returning count. On the poll after 252 it found duplicates and raised, so loop never saw successful 256 completion; finally immediately requested OFF. No intentional wait for duplicates; no native completion notification/frozen first-set storage exists. Count/statistics are separate snapshots. Callback has no device API access; existing preallocated storage path unchanged.

Per user's explicit if-and-only-if ordering condition, production first-sequence/shutdown_spillover acceptance, sample freeze, completion wake-up and metadata changes are deferred. No duplicates relabeled/ignored. Requested spillover-success/immutable-first-samples tests cannot validate a production policy whose ordering prerequisite remains unresolved; conservative rejection remains. Before a future separately authorized run, review bounded OFF-preallocated chronology instrumentation with cycle/frame/sequence/header validity, overflow handling and worker OFF-request/return markers. No hardware authorized by this diagnostic.

Files created: artifacts/phase5_stage3d/order_diagnostic.md (chronology/source/limits), tests/test_ui_stage3d_order_evidence.py (four pure evidence/regression cases). File modified: AGENTS.md only. Original evidence, production GUI/backend/native code, verified configs, backup_original.txt, network and saved data unchanged. Tests demonstrate aggregate ambiguity, ascending-order non-identifiability, retained duplicate/missing/unexpected/malformed rejection. No hardware-capable tool/test executed.

Exact commands using specified Python: -m unittest discover -s tests -p 'test_ui_*.py' -q -> 140 passed; -m unittest discover -s tests -p 'test_tfm_offline.py' -q -> 20 passed. Total **160 passing**, preserves 156 baseline plus four new cases. -m py_compile tests/test_ui_stage3d_order_evidence.py passed. STOP; do not reacquire or implement spillover exception automatically.

### Stage 3D attempted once; FAILED duplicate-record acceptance and safely stopped - 2026-10-08

This is the active checkpoint. The user's one Stage 3D authorization was used for exactly one production-GUI acquisition-enable sequence. Repeated Stage 3C preflight PASSED, but duplicate callbacks were observed, so the experiment STOPPED OFF with no retry and no dataset save. Do not start another acquisition, change parameters or begin B-scan/TFM acceptance. Physical firing count remains unknown. Report this failure, not a successful complete acquisition.

Actual command: specified Python tools/validate_phase5_stage3_acquisition.py, approved desktop execution once, exit 1. UTC 2026-10-08T20:28:53.255570..20:30:10.669171; acquisition-enable request 20:30:09.088258. Exactly one unchanged hash-matched fmc16_full.txt application via existing OFF/reconnect AOS path; all load stages true, parsed count 256. All readable topology/timing/acquisition/gain/filter/aperture fields matched Stage 3C; three SDK-unreadable categories actual None with 288 applied_configuration evidence fields. GUI revision 9 reached Verified (mixed sources), FMC-ready. OFF storage prep succeeded for 256x3001 one-byte samples=768256 bytes plus 3001 single-buffer bytes. Acquisition operation repeated normal OFF readback/prep before one LockDevice/UnlockDevice(eAcqOn) start. No verification bypass, warning dialog or config mismatch.

At rejecting poll: 256 unique required cycles, total 268 callback records, 12 duplicate callbacks at IDs 0..11; no missing/unexpected/native-malformed records. Last successful progress poll had 252 unique cycles; next poll already included all 256 plus duplicates. Guard raised immediately and existing acquisition finally-stop succeeded. Final post-stop local counters: total 284, duplicate callbacks 28; IDs 0..27 twice, 28..255 once, missing=[], unexpected=0, malformed=0. Additional callback arrival was observed by the final counter read during stopping; there was no second acquisition-enable call. Frame IDs were not captured, so do not claim whether repeats were a subsequent physical frame or another delivery mechanism. Physical pulse count is not established.

Header checks on 252 records passed 3001 points, data size 1 byte, signed true, bit-size enum 0. Final four headers were not individually checked because duplication caused immediate abort. No raw NumPy matrix/FMC cube/result metadata was accepted or produced; no new .npy/sidecar saved, no save/reload/selector/completed-display acceptance. Do not claim expected (256,3001)/(16,16,3001)/int8 as captured successful arrays. No waveform interpretation or B-scan/TFM processing/acceptance occurred on this rejected run.

GUI remained responsive: 18 monotonic progress events 2/256..252/256 then error; no successful completion. Acquisition-operation UI ticks 606, max interval 0.0762743 s (includes OFF verification); total heartbeat 1276, max 0.500042 s including initial schedule. Safety cleanup completed: first successful OFF immediately after rejecting poll (API entry 1378), repeated OFF before disconnect, final cleanup OFF timestamp 20:30:09.938022; clean_close=true, acquisition_off_at_close=true, protected_files_unchanged=true. Disconnect, handle/storage destruction and Tk close succeeded. All pre-existing config/data SHA-256s unchanged, including backup_original/fmc16_full/historical FMC. No dedicated FMC, shot unlock, text writer, network or probe-assumption change. Single-run tool refuses a recorded previous attempt.

Failure classification: acquisition polling/native record-admission boundary (Python backend/local bridge storage) with repeating AOS callback delivery. Existing per-cycle storage overwrites duplicates and ordinary count only counts unique slots; acceptance instrumentation detected repeats. Poll/stop latency plausibly permits initial IDs to recur before OFF, but exact AOS frame behavior/device fault is not proved. No other hardware test or compensating code/parameter change after failure. Preserve prior successful connection/config/readback stages.

Changes made before hardware: local callback total/per-cycle/duplicate/unexpected/malformed counters (including null headers) under existing mutex, OFF clear reset, additive read-only statistics export/ctypes helper; no callback device access/allocation. Copy/preallocation/SDK start/stop paths preserved. Explicit metadata cycle mapping and visible physical mapping status; synthetic save/load tests only (no accepted real dataset). Created guarded tools/validate_phase5_stage3_acquisition.py and tests/test_ui_stage3d_offline.py; modified bridge header/source/generated build outputs, oempa/api.py, oempa/dataset.py, ui/presentation.py, tests/test_ui_native_wrapper_offline.py, tests/test_ui_fmc_provenance.py, AGENTS.md. No acquisition.py/GUI/controller/verifier/config writer or verified file changes. Full evidence/result: artifacts/phase5_stage3d/validation.json and result.md; four preflight screenshots preserved.

Validation before/after attempt: cmd /c bridge\build_bridge.cmd succeeded (existing C4005/C4091 warnings); seven-file py_compile passed. Restricted offline python -m unittest discover -s tests -p 'test_ui_*.py' -q -> 136 passed; separate -p 'test_tfm_offline.py' ->20 passed, total 156 preserves 151 plus five new fake/pure counter-boundary tests. No hardware-capable test discovery ran. STOP here; no automatic retry or additional acceptance stage.

### Stage 3D explicitly authorized; single-run preparation - 2026-10-08

Active scope: user explicitly approved one controlled complete FMC acquisition through production GUI/backend after repeating unchanged hash-matched file application, OFF readbacks/strict mixed-source verification and 256x3001 callback preparation. No retry or second start, no B-scan/TFM acceptance or physical interpretation. Prior stop-before-acquisition wording is superseded only for this single Stage 3D run. Any readable mismatch prevents start; acquisition/callback anomaly must stop OFF with no dataset save.

Inspected current SDK stream header (cycle/dataCount/dataSize/sign/bitSize/MAX validity), native callback/local storage, unchanged LockDevice -> UnlockDevice(eAcqOn/eAcqOff), acquisition polling/finally-stop, GUI controller/result/persistence and field provenance. Existing per-cycle storage overwrites duplicates and counts only distinct received records. Added local per-record callback counters plus total/duplicate/unexpected/malformed counters and additive read-only export/ctypes wrapper so acceptance can detect rather than conceal repeats/out-of-range IDs. Counters use existing preallocated record storage under the local mutex, no SDK call/resize in callback. Clear resets counters OFF. Existing SDK acquisition/control/copy path is otherwise preserved. Acceptance runner rejects anomalies at polls and after OFF, verifies all 256 headers and raw/FMC equality, invokes production save only on success to a new timestamped filename, then reloads offline and cleans up. Guard permits only one load and one start; a recorded prior run prevents automatic re-execution. Exact physical firing count is not inferred from records.

Created tools/validate_phase5_stage3_acquisition.py and pure tests/test_ui_stage3d_offline.py; added two fake-DLL boundary tests. Metadata now carries explicit cycle mapping and dataset summary shows physical mapping status; mixed-source field evidence stays intact. Callback collection logic gains counters only; no hardware setters/config values changed. Initial/final build succeeded with existing C4005/C4091 warnings. Final pre-execution offline 136 UI +20 TFM =156 passed preserving 151 plus five tests; seven-file py_compile passed. Null-header callbacks are also counted as malformed, and the new export contains exceptions within the C boundary. Hardware has not been accessed in this task. Next authorized command is specified Python tools/validate_phase5_stage3_acquisition.py once; stop after the one attempt, successful or failed.

### Final Stage 3C completed; acquisition approval pending - 2026-10-08

This is the active checkpoint. Final narrow policy and production-GUI OFF preflight PASSED. STOP before acquisition and request explicit approval for Stage 3D. No acquisition was enabled. User-authorized exception applies only to exact successfully applied configs/fmc16_full.txt MultiHWChannel classification and base TX width/delay. Their actual values remain None, with separate applied_configuration field evidence; full hardware-readback verification remains false. All other required readbacks must be present and match. Any readable TX/ordinary mismatch still blocks. Physical probe/channel mapping remains Unverified.

Actual command: specified Python tools/validate_phase5_stage3_preflight.py, approved desktop execution, exit 0; UTC 2026-10-08T20:13:04.194367..20:13:45.521494. Exactly one unchanged file application using the established AOS OFF/reconnect path; SHA-256 0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7. All load stages true, parsed count 256. No API error or observed SDK modal warning/error; modal monitoring is not a complete vendor warning stream. All 556 guarded API calls succeeded on worker threads. No new setter or getter experiment; source inspection only established omitted TX Delay zero defaults for applied-law provenance.

Observed all 256 cycles: CycleCount 256; MultiChannel supported/enabled true; analog/digital/beam 20/0/0 dB; Start 0 us selected from hardware base start arrays using applied grouping/RX selection; Range 30 us; TimeSlot 2000 us; PointCount 3001 (file requests automatic 0); sampling 100 MHz; PointFactor 256; Compression/Signed/8-bit enums 0/0/0; filter 1. All base TX apertures, replay-empty TX and selected RX apertures match cycle=tx*16+rx. Base MultiHW start arrays sixteen zeros and packed decimation eight zero bytes. All hardware classification values None; all sixteen base width/delay readbacks None. Separate applied evidence supplies 256 flags and sixteen widths 0.5 us / sixteen zero delays. No readable mismatch, uncovered required-unavailable field or getter error. Pulser-power max/current observations 15/0 W, not required configuration power.

Production state at revision 9: configuration_verified true, readback_verified false, label Verified (mixed sources); acquisition_ready true while connected, Acquire enabled but never invoked, Stop disabled. Requested and actual remain separate; mixed-source notice and real-readback screenshot visually reviewed. Only after verification, existing OFF -> count 256 -> register -> clear -> preallocate succeeded: 256 x 3001 one-byte samples = 768256 cycle bytes plus 3001 single-buffer bytes. Expected raw (256,3001), FMC (16,16,3001), int8; no captured data exists. Callback static inspection confirms no device API access and no resize in preallocated branch. Acquisition remained OFF and zero callback records arrived; no firing/acquisition was initiated (no independent physical pulse monitoring). No EnableFMC, SetUnlockEnableShot, OEMPA_WriteFileText, network/config-file/data-file change.

Cleanup completed: OFF, disconnect, handle release, normal window close; no worker remains. Buffers were released with the handle; a later explicitly approved run must reconnect/reverify and prepare again OFF before start. clean_close/protected_files_unchanged/passed true, errors/vendor_dialogs empty. UI heartbeat 648 ticks, max interval 0.512725 s including initial schedule. Full acquisition-critical Field/Expected/Observed/Provenance/Status table, remaining unavailable/not-applicable fields and exact commands: artifacts/phase5_stage3c_final/checkpoint.md; live full snapshot/API/field evidence: validation.json; five screenshots preserve initial, connected, Verified and disconnected UI.

Files modified: oempa/hardware_state.py (three-field whitelist, exact path/hash/parameters/topology guards), oempa/verified_fmc.py (parsed base/replay aperture/width/omitted-delay structure), oempa/gui_backend.py and gui.py (honest scope/notice), tests/test_ui_fmc_provenance.py and tests/test_ui_backend_offline.py, tools/validate_phase5_stage3_preflight.py and AGENTS.md. New final preflight artifacts. No native/bridge/DLL/acquisition/config writer changes or build. Repaired one prior non-UTF8 checkpoint byte without content loss.

Offline tests: python -m unittest discover -s tests -p 'test_ui_*.py' -q -> 131 passed; python -m unittest discover -s tests -p 'test_tfm_offline.py' -q -> 20 passed. Total 151 preserves all 148 baseline cases plus three new focused cases. Existing cases strengthened for metadata actual None/applied sources/unverified mapping, adapter allocation, and unrelated missing readbacks; new cases cover exact whitelist/invalid provenance, readable TX and ordinary mismatches and PA/unapproved-mode exclusion. Seven-file py_compile passed. No hardware-capable tests/general discovery ran. Future dataset metadata persistence was verified with synthetic temporary arrays only. STOP at this checkpoint; Stage 3D physical FMC acquisition needs explicit user approval.

### Final Stage 3C policy implementation / OFF preflight pending - 2026-10-08

This is the active checkpoint. The user accepted the TX diagnostic and explicitly authorized final FMC verification and one unchanged-file application/readback/preallocation, acquisition OFF. This supersedes prior classification-only/no-TX-exception stop wording only for the three documented unreadable MultiHWChannel fields: HWAcq/replay classification and base-cycle TX widths/delays. Actual hardware values remain None; applied evidence is source applied_configuration, never hardware_readback. Exact repository file path/hash, successful completed AOS parsing/application stages, OFF state, internally valid 16x16 grouping, strict readable topology/timing/gain/format/filter/aperture comparisons and no other required-unavailable field are required. Readable TX values, if supplied, still must match; no mismatch can be masked. Width comes from parsed 0.5-us file value; absent TX delay has zero semantics established by vendor ReadFileTextMultiHWChannel (CustomizedDriverAPI.cpp:4233..4236), followed by the existing SetEmissionDelays path. No new getter investigation or hardware setter is introduced.

Added three focused offline cases and strengthened existing metadata/adapter/missing-field cases. Mixed-source metadata preserves all three applied sources and actual None values, and physical mapping remains Unverified. UI notice/scope now identifies classification and base TX width/delay together. New preflight artifacts use artifacts/phase5_stage3c_final, preserving failed runs. Callback prepare remains after successful verification only, with existing OFF -> set count -> register -> clear -> allocate mechanism. No native/bridge/callback or acquisition behavior change. Physical acquisition remains prohibited and requires explicit approval after the observed Stage 3C checkpoint. Preflight hardware execution pending. Offline UI suite: 131 passed; separate TFM suite: 20 passed; 151 total preserves the 148 baseline plus three cases. Syntax checks passed for seven affected Python files. Repaired a single mixed-encoding byte in a prior appended AGENTS checkpoint to UTF-8 without changing content.

### Stage 3C provenance policy implemented; preflight STOPPED on additional unavailable TX readbacks - 2026-10-08

This is the active checkpoint. The specifically authorized classification policy is implemented and software-tested, and one unchanged-file OFF application/readback was attempted. Stage 3C acceptance is NOT complete: independently required TX widths and TX delays are unavailable for all sixteen base cycles. Their fields do not receive the classification exception, so readiness remains false. No acquisition enable, callback registration/preparation/storage allocation/resizing, dedicated FMC, shot unlock, text writer, network or parameter adjustment occurred. STOP here; do not retry/reapply/acquire automatically or extend the provenance exception to these fields.

Actual command: approved desktop `python tools/validate_phase5_stage3_preflight.py`, exit 1, UTC 2026-10-08T19:18:21.853084 through 19:19:01.766127. Production GUI Connect succeeded at 192.168.1.11:5001 with CycleCount 256 and MultiHWChannel supported/enabled. Exactly one existing `configs/fmc16_full.txt` load used unchanged driver/AOS OFF/reconnect path. Load stages entered/before_hw/after_hw/left all true; parsed count 256. File remains SHA-256 `0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7`. Global and all 256 cycle readbacks were captured. No observed SDK modal warning/error; the modal monitor is not a complete AOS warning stream.

Observed checkpoint (not acquisition metadata): CycleCount 256; MultiHWChannel supported/enabled true; analog/digital gains 20/0 dB and beam correction 0 dB on all cycles; effective Start 0 us from base MultiHW start arrays and provenance-selected RX (not normal GetAscanStart substitution); Range 30 us; TimeSlot 2000 us; PointCount 3001; sampling 100 MHz; PointFactor 256; Compression enum 0; Signed rectification enum 0; 8-bit enum 0 (expected int8, one byte/sample); filter 1. Base start arrays have 16 zeros and decimation packed bytes are zero. All requested logical TX/RX aperture mappings match; expected raw shape (256,3001) and FMC shape (16,16,3001); cycle=tx*16+rx. These are expectations, not captured arrays. Callback storage was NOT prepared because validation stopped first: expected eventual 256 records x 3001 bytes = 768256 cycle-buffer bytes, plus 3001-byte single-buffer storage; currently no allocation from this run can be claimed.

HWAcq/replay classification: exact parsed/applied file provenance only, base cycles 0,16,...,240 HWAcq, remaining replay. Hardware snapshot hw_acquisition is None for every cycle; each field is Unavailable due documented AOS SDK output limitation, not False, mismatch, or hardware-readback verified. Separate classification evidence is applied_configuration_verified, with source path/hash, parsed 256 flags, requested parameters and completed load stages retained. This exception is limited to the exact approved file and classification only. Full hardware readback verification remains false; successful mixed-source configuration verification is possible only when all remaining required fields are independently readable/matching. Required unavailable fields block it without inventing a readable mismatch.

New blocker, every base cycle 0,16,...,240:

| Field | Requested | Read back | Interpretation |
| --- | --- | --- | --- |
| TX widths | 0.5 us on the selected logical TX | None | Required readback unavailable; no provenance exception |
| TX delays | zero | None | Required readback unavailable; no provenance exception |

Each base's independent extended getter was called with multi_channel=False (read selector only, not hardware mode change). It returned API success but Python decoded widths/delays None, which represents native -1 counts. Static header comparison: GetEmissionWidths/GetEmissionDelays each take (int cycle, int& capacity, int* count, float* data); existing bridge calls that exact signature with capacity 16, count initialized -1 and separate bool return. MultiHW classification/start/decimation calls are skipped in this independent read; therefore the known classification seed cannot gate TX reads here. No output-count seed diagnostic or alternative SDK getter experiment was performed. The underlying count/readback failure remains unresolved at extended bridge/AOS SDK boundary (layers 4/5); verification/controller correctly refused readiness. Do not claim these TX fields are proven SDK-unreadable merely from this run, and do not widen the exception. Hardware/device representation remains possible.

Other unavailable/not-applicable snapshot fields are PA receive focusing, DDF, receive delays/gains/focal TOF and emission/reception wedge delays; replay TX emission fields are not required. Identity/firmware/serial are not newly read; required configuration power is not exposed here (pulser-power observational getter was not reached after failure). Probe identity/physical channel mapping and geometry remain unverified. Every field's source/status is retained in the full snapshot evidence; hardware-derived Start includes its dependency on applied grouping.

Cleanup: serialized worker forced OFF, disconnected and destroyed handle; normal controller shutdown completed, no owning worker/device remained, Tk window closed. clean_close=true; protected_files_unchanged=true for all configs/data including backup_original and historical FMC. 549 permitted Python API calls returned successfully; no callback storage API or acquisition-enable call occurred. Heartbeat count 647, max interval 0.505292 s including initial schedule. GUI remained unverified/not ready; no screenshot of a ready checkpoint exists. Original live report (before final unavailable-vs-mismatch wording refinement) retains 32 required-missing entries under historical verification_mismatches. Offline re-evaluation of the captured snapshot with current semantics reports 0 readable mismatches, 32 required-unavailable fields and verified=false. This involved no SDK/device import/call or hardware rerun. Evidence: artifacts/phase5_stage3c_provenance/validation.json and offline_reassessment.json; prior failed-stage artifacts were preserved.

Files created: tests/test_ui_fmc_provenance.py and new preflight artifact directory. Files modified: oempa/hardware_state.py, oempa/verified_fmc.py, oempa/api.py, oempa/gui_backend.py, oempa/dataset.py, ui/state.py, ui/controller.py, gui.py, tests/test_ui_backend_offline.py, tests/test_ui_native_wrapper_offline.py, tests/ui_readback_fakes.py, tools/validate_phase5_stage3_preflight.py and AGENTS.md. Field evidence and applied file provenance round-trip through existing .npy + JSON metadata path in temporary synthetic tests; no real dataset was acquired/saved. Original bridge/DLL/callback/acquisition/configuration loader/verified files were not changed or rebuilt in this task. No HW snapshot mismatch is silently accepted; unknown fields are not substituted from configuration except the specifically approved classification policy.

Final offline validation: inspected software-only `python -m unittest discover -s tests -p 'test_ui_*.py' -q` passes 126 tests, and `python -m unittest discover -s tests -p 'test_tfm_offline.py' -q` passes 20, total 146 preserving all 134 plus 12 focused cases. Syntax checks pass for 13 affected Python files. New cases cover seed-preserving output unusability, None preservation, applied-vs-hardware field evidence, actual/readable mismatch readiness block, narrow exception, missing TX readback block, failed/ineligible apply provenance, mixed-source state/dirty gate, independent TX/start reads, offline metadata round-trip and adapter preallocation ordering/failure. No hardware-capable test_ diagnostic/general discovery ran. STOP before Stage 3C completion or acquisition; future TX getter diagnostics need a separately scoped instruction.

### Stage 3C provenance policy implementation / preflight pending - 2026-10-08

The user authorized this specific configuration-provenance exception and one unchanged FMC-file reapplication/readback/preallocation with acquisition OFF, stopping at Stage 3C. This supersedes previous no-retry wording only for this explicit scope; physical acquisition remains unauthorized. Known SDK-unreadable HWAcq/replay output is `None`, never False or hardware verified. Only the exact approved 256-cycle FMC file's parsed flags may supply classification, after successful complete AOS load/parse stages and OFF confirmation. Applied source path/hash/parsed flags/requested parameters remain distinct from hardware snapshot fields. Other missing/failed/mismatching required getters still block readiness; no arbitrary unavailable field exception. Hardware-read start arrays and TX widths/delays are read independently of broken classification. Point count/rate/factor/8-bit are separately checked against previous effective acceptance values of this exact automatic-count file, never written into the file/device. Field evidence distinguishes hardware_readback_verified, applied_configuration_verified, unavailable, mismatch and observed (not compared). Application state has separate mixed-source configuration verification and readback verification; mixed-source success never sets readback_verified true. Metadata retains full per-field evidence and file provenance through sidecar save/load.

Software implementation/testing underway; no hardware call or write yet in this task. Existing native callback, acquisition implementation, SDK loader/configuration write mechanism and bridge/DLL are unchanged. Hardware preflight must stop on any SDK warning or readable mismatch, allocate callback storage only OFF after verification, disconnect safely and report exact live values. No acquisition enable, dedicated FMC, shot unlock, file rewrite/network adjustment or physical interpretation is allowed.

Pre-execution validation: restricted offline UI suite passed 126 tests, separate TFM suite passed 20 (146 total, prior 134 preserved plus 12 new focused tests); syntax checks passed for 13 affected Python files. A previously simplified FMC fixture used 0-dB replay analog readbacks; updated only that fixture to the actually documented 20-dB replay readback for the exact approved file. New all-cycle gain check remains strict. File requested values remain 256 cycles; MultiHWChannel enabled; base flags 0,16,...,240 true, other flags false; range 30 us; automatic PointCount 0; Signed; filter 1; gains 20/0 dB on acquisition cycles; beam correction 0; hardware/replay TimeSlot 2000 us; width 0.5 us; base start arrays and decimation zero. SHA-256 remains 0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7. Opt-in production GUI preflight now records mixed-source evidence and uses a new artifact directory to preserve prior failed-stage evidence. No hardware action has occurred yet.

### Read-only MultiHWChannel diagnostic completed: output is seed-dependent - 2026-10-08

This is the active checkpoint; Stage 3 remains STOPPED before acquisition. Direct read-only diagnostic ran 2026-10-08 18:59:03-18:59:06 UTC with the existing hardware state, no configuration load/write, no callback registration/preparation/storage resizing, and acquisition OFF throughout. CycleCount read 256; MultiHWChannel supported/enabled. For every selected cycle, getter success and unlock success were true for both valid initial bool values; the output remained equal to its initial value:

| Cycle | File HWAcquisition | Success (both reads) | Output seeded False | Output seeded True |
| --- | --- | --- | --- | --- |
| 0 | 1 | True | False | True |
| 1 | 0 | True | False | True |
| 15 | 0 | True | False | True |
| 16 | 1 | True | False | True |
| 17 | 0 | True | False | True |
| 31 | 0 | True | False | True |
| 32 | 1 | True | False | True |
| 240 | 1 | True | False | True |
| 241 | 0 | True | False | True |
| 255 | 0 | True | False | True |

The direct bridge invokes ONLY the exact getter inside the device lock, then unlocks; no start/decimation/width calls can overwrite the local bool. Inference: installed SDK getter is not providing a usable cycle classification in this connected state; previous false-initialized extended snapshot values are not proof all cycles are replay. Existing bridge signature, native bool/output handling and ctypes C-int boundary match the installed declarations. No readback bug in those bindings was established; production snapshot/verifier/acquisition behavior was not changed or weakened. This characterizes the discrepancy but does not establish the actual hardware HWAcq/replay state or explain the SDK implementation. Likely unresolved boundary: AOS SDK implementation/driver cached state, possibly device readback semantics; binary implementation is not exposed in searched sources. A reconnect-only diagnostic cannot prove whether the prior write transformed state. Do not substitute file expectations or seeded True values for hardware truth.

Vendor `CustomizedDriverAPI.cpp:1677` calls this getter whenever root MultiHWChannel is enabled, including replay cycles, and uses its output for HWAcq/replay branching. Ordinary cycles are distinguished by global MultiHWChannel disabled. `:2459` programs the file's flag with `EnableMultiHWChannelAcquisition(iCycle, root CycleCount, bHWAcquisition)`. The C# wrapper at `csDriverOEMPA.cpp:7742` simply forwards the getter. Searches of installed source/header definitions found no alternative MultiHWChannel cycle-type getter or exposed native implementation. Dedicated FMC replay subslot getters describe timing, not this cycle type, and were not used.

Added diagnostic-only native export in bridge header/source and ctypes helper in `oempa/api.py`, plus guarded `tools/diagnose_multihw_readback.py` and two fake-DLL offline tests. Native export exposes getter success, output state and unlock success separately as C integers; C++ bool stays inside native code. No new hardware write mechanism. Built with `cmd /c bridge\build_bridge.cmd`: success, existing C4005/C4091 warnings only; DLL/obj/lib/exp rebuilt. Ran `python tools/diagnose_multihw_readback.py` once: clean disconnect/handle destruction, protected configs/data hashes unchanged. Complete evidence: `artifacts/phase5_multihw_readback/diagnostic.json`. No acquisition enable/prohibited API call occurred. Higher-level HardwareSnapshot/FMC verification was NOT rerun because the direct getter does not identify the expected pattern reliably.

Offline validation: `python -m unittest discover -s tests -p 'test_ui_*.py' -q` passed 114 tests; `python -m unittest discover -s tests -p 'test_tfm_offline.py' -q` passed 20 tests. Total 134, preserving prior 132 plus two getter-boundary tests. Python syntax checks passed for API, diagnostic and edited fake-DLL test. These suites use offline/pure/fake backends; no hardware diagnostic tests were included. STOP here; no Stage 3C readiness, new FMC frame or dataset acceptance is established.

Installed `UTKernelDriverOEMPA.h` declares `bool GetEnableMultiHWChannelAcquisition(int iCycle, bool *pbEnable)`: return is operation success, output is acquisition state; no cycle count is required. `CustomizedDriverAPI.cpp:1677` reads that output for MultiHWChannel cycle classification; the C# wrapper forwards the same signature. Setter is `bool EnableMultiHWChannelAcquisition(int iCycle, int iCycleCount, bool bEnable)`. Write-start setter is `bool SetMultiHWChannelAcqWriteStart(int iCycle, int iAcqElement, int iStartCount, float *pfStart)` (also callback-array overload); starts begin at probe element #1, no gaps. No separate ordinary/HWAcq/replay type getter was found: vendor uses global MultiHWChannel enable plus per-cycle acquisition output. Current bridge uses success and output correctly; ctypes carries C integers, not native C++ bool pointers. A separate getter-only export will compare false/true initial output values without changing production verification. No configuration write, callback storage change or acquisition is authorized.

### Phase 5 Stage 3B stopped on FMC readback mismatch - 2026-10-08

This is the active checkpoint. The user authorized only Stage 3A-3C and explicitly required stopping before acquisition approval. Stage 3A passed file inspection; Stage 3B loaded successfully but FAILED FMC mode-specific verification. STOPPED with acquisition OFF; no Stage 3C readiness approval/checkpoint or Stage 3D acquisition is established. No acquisition enable, callback registration/preallocation/storage mutation, prohibited API, network change, file modification, acquisition or dataset save occurred in the real-device run. Do not retry/apply/enable automatically.

Command: approved desktop `& '<python>' tools/validate_phase5_stage3_preflight.py`, exit 1. UTC start 2026-10-08T18:46:20.333389, finish 18:46:59.405250. Production GUI Connect reported initial prior PA state: CycleCount 1, MultiChannel supported true / disabled. Exactly one unchanged `configs/fmc16_full.txt` application used the established driver/AOS OFF/reconnect path. Load diagnostics all true (entered/before_hw/after_hw/left), parsed_cycle_count 256. Reconnected status: CycleCount 256, MultiChannel supported true / enabled true. Both normal and extended snapshots were read for all 256 cycles; no getter error was reported. No observed vendor modal dialog. No parameter adjustment, second write or hardware diagnostic/reconnect was attempted after failure.

Recorded actual common values for all 256 cycles: Range 30 us, TimeSlot 2000 us, PointCount 3001, sampling 100 MHz, PointFactor 256, Compression enum 0, Signed enum 0, 8-bit enum 0, analog gain 20 dB, digital gain 0 dB, beam correction 0 dB, filter 1. Normal A-scan Start read 0, and each extended MultiHW start array contained sixteen zero values; packed decimation eight bytes all zero. Normal Start is not substituted for the required captured MultiHW replay timing. Logical TX/RX aperture mapping readbacks did not produce a mismatch. File requests automatic PointCount 0, Signed, range/filter/gains/times above; current readbacks are observations, not acquisition metadata.

Blocking mismatch:

| Field | Requested | Read back | Interpretation |
|---|---|---|---|
| Base-cycle hw_acquisition, cycles 0,16,...,240 | true | false on all 16 | Cannot establish hardware-acquisition/replay ordering |
| Derived start_s, all 256 cycles | 0 seconds | unavailable/None | No acquisition base cycle identified, so group/replay timing cannot be established |
| Base-cycle widths_s | 0.5 us | unavailable/None | Extended native reader skips TX fields when getter reports replay |
| Base-cycle tx_delays_s | zero | unavailable/None | Same conditional skip; not proof of nonzero delays |

559 reported mismatches include the above and cascading shared-start unavailable comparisons; do not describe them as 559 independent hardware failures. Actual hardware snapshot and requested values are retained in UI state/report, but configuration stayed Unknown/unverified and Acquire disabled. Callback prepare is reached only after verification; it was not called, so neither 256 callback records nor sample buffers were prepared during this failed run. No captured waveform/shape/dtype can be claimed. Expected eventual raw (256,3001), cube (16,16,3001), signed int8/1-byte samples remain conditional expectations only.

Smallest diagnostic performed after cleanup was offline inspection of recorded JSON and bridge/Python/SDK source. Native OEMPA_GetExtendedCycleSnapshot calls documented GetEnableMultiHWChannelAcquisition(int,bool*), uses that boolean to decide whether TX widths/delays are read, then assigns it into the returned struct. Python decodes that integer to bool; fake-DLL layout tests already cover the struct. Vendor CustomizedDriverAPI.cpp uses the same getter at line 1677 and the corresponding EnableMultiHWChannelAcquisition setter in its existing file write at line 2459. No obvious signature mismatch was identified by this static review. Classification: failure manifests at the C++ extended-readback / AOS MultiHWChannel getter boundary (layers 4/5); actual device flag/config behavior (layer 6) remains possible. Metadata verification/state (layers 2/1) correctly rejected the inconsistent report. Python acquisition/callback storage (layers 3/4 acquisition side) were never exercised. Do not infer hardware is truly replay-only or replace reported flags with expected index patterns without evidence. A separately scoped read-only diagnostic may later distinguish direct getter/call ordering/cache/readback semantics; none has been run now.

Cleanup succeeded: OFF twice before final disconnect, disconnect and handle destruction on the serialized worker; app shutdown_complete true, no active operation, device cleared, window closed. All 532 permitted Python API calls succeeded at API return level, notwithstanding the verification mismatch. protected_files_unchanged=true (all config/data SHA-256 inventory matched, including verified FMC file, backup_original and historical fmc16x16.npy); clean_close=true; report passed=false. Device was left with the successfully loaded FMC file and acquisition OFF; no restoration write was attempted. JSON and initial disconnected/connected screenshots are under artifacts/phase5_stage3_preflight; no Verified screenshot exists because verification failed.

Code additions made before this acceptance attempt: new pure `oempa/verified_fmc.py`, new opt-in `tools/validate_phase5_stage3_preflight.py`, additive existing-file adapter/GUI entry points in oempa/gui_backend.py and gui.py, and optional trailing callback_capacity_bytes argument in oempa/acquisition.py. Existing native preallocation is now usable after OFF -> set record count -> register if necessary -> clear -> preallocate; clear/register empty the sample vectors, so preallocation must follow them. Production backend passes capacity derived from captured point count and bit-size to later acquisition preparation. No native callback/device setter/SDK write mechanism changed and no bridge rebuild occurred in this task. PA acquisition gate remains unchanged. Tests/test_ui_backend_offline.py adds two offline cases for file preservation/no regenerated writer and exact OFF/clear/preallocate ordering. AGENTS.md updated. An initial test-harness Mock aggregation error was corrected before execution.

Offline regression after production changes: `python -m unittest discover -s tests -p 'test_ui_*.py' -q` passed 112; `python -m unittest discover -s tests -p 'test_tfm_offline.py' -q` passed 20, preserving the 130 baseline plus two focused cases. `python -m py_compile gui.py oempa/gui_backend.py oempa/acquisition.py oempa/verified_fmc.py tools/validate_phase5_stage3_preflight.py tests/test_ui_backend_offline.py` passed. No general discovery/hardware-capable test_ diagnostic was run.

Next action: report Stage-3B failure and STOP. Stage 3C cannot be approved yet: configuration is unverified, acquisition readiness false, callback storage not prepared. Do not request firing approval until this readback discrepancy is resolved and all pre-acquisition checks pass. Preserve the single successful file load and earlier stages, do not modify gain/width/TimeSlot/mapping to compensate. Probe/channel mapping remains Unverified.

### Phase 5 Stage 3A inspection / 3B preparation in progress - 2026-10-08

The user authorized only FMC existing-file application/readback and pre-acquisition checkpoint 3A-3C; no acquisition enable is authorized. Read AGENTS.md completely and inspected production configuration/acquisition/state/native callback/preallocation paths. Existing configs/fmc16_full.txt SHA-256 `0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7`: Root CycleCount 256, EnableMultiChannel 1; all 256 logical mappings checked; hardware cycles 0,16,...,240, one TX per group, RX0 on base then RX1..15 replay; all starts/decimation zero, common range 30 us, automatic PointCount 0, Signed, filter 1, digital/beam 0 dB, hardware analog 20 dB, hardware/replay duration 2000 us and TX width 0.5 us. File omits explicit normal start/compression/bit-size keys; read actual values after load, do not invent them. No file regenerated or changed.

Minimal integration adds a hash-bound read-only FMC file inspector and explicit production adapter/GUI existing-file application entry point through the unchanged driver/AOS OFF/reconnect path. Native preallocation already exists and suppresses callback resizing. Production acquisition prepare previously sized the outer 256 records but resized sample storage in the callback; use existing prepare_ascan_callback_buffers after set-count/register/clear (register and clear both empty sample storage) while OFF, with capacity from actual point count/encoding. An optional trailing acquisition argument preserves public compatibility and allows the production adapter to repeat safe OFF preparation before any later explicitly approved start. No callback/API/native hardware setter changes. Full FMC mode verification and callback preparation must succeed before state Verified. Hardware execution is pending; stop on any failure, no Stage 3D.

### Phase 5 Stage 2 completed - 2026-10-08

This is the active checkpoint. Completed the user's Stage-2-only authorized real-device application/readback of the existing 0-degree PA 2600-us Compression file. STOP here; no A-scan/FMC/PA acquisition or Stage 3 is authorized. Prior software-only/Stage-1 stop wording is superseded only for this completed configuration application with acquisition OFF. No acquisition-enable call, callback registration/storage preparation, prohibited API, network change, configuration-file modification or saved-data modification occurred.

Actual command: `& '<python>' tools/validate_phase5_stage2.py`, approved desktop execution using the established healthy Tk runtime. Exit 0; UTC 2026-10-08T17:55:11.783704 through 17:55:19.029803. The production GUI's Connect succeeded at 192.168.1.11:5001. Initial and pre-write status both read CycleCount 1, MultiChannel supported true / enabled false. Exactly one application of the unchanged approved file used OEMPADevice.load_configuration(reconnect=True) -> existing OEMPA_LoadConfiguration -> OEMPA_ReadFileWriteHW(..., eAcqOff). All load diagnostics true: entered, before_hw, after_hw, left; parsed_cycle_count 1. Existing OFF/disconnect/reconnect/OFF sequence succeeded. No observed SDK modal warning/error; no callback error/traceback. Modal monitoring is not a complete vendor warning stream, which remains deferred.

Stage-2A requested values were reported before any hardware write. The file still has SHA-256 `70a13245d7231d12b5f824965e6066918e8e61137f7575446c2699364239caa9`. It requests PointCount 0 (automatic), not an explicit 3001 or sampling frequency. Automatic output expectations below come from the prior verified candidate and are checked separately from the file request, not entered as GUI constants or written back to the device.

Stage-2C actual snapshot, all required comparisons passed with zero mismatches/read errors:

| Field | Requested / prior effective expectation | Actual readback |
|---|---|---|
| CycleCount / MultiChannel | 1 / already disabled (file omits key) | 1 / disabled; supported true |
| Start / Range / TimeSlot | 0 / 30 / 2600 us | 0 / 30 / 2600 us |
| PointCount | 0 automatic; previous effective 3001 | 3001 |
| Sampling / PointFactor | previous effective 100 MHz / 256 | 100 MHz / 256 |
| Compression / Rectification / Bit size | Compression / Signed / previous 8-bit | enums 0 / 0 / 0, Compression / Signed / 8-bit |
| Analog / Digital / Beam correction | 20 / 0 / 0 dB | 20 / 0 / 0 dB |
| Filter | 1 | 1 |
| TX / RX aperture | logical 0..15 / 0..15 | logical 0..15 / 0..15 |
| TX / RX delays | sixteen zeros / sixteen zeros, one law | all zero / all zero |
| RX focusing / laws / DDF | Standard / one / static | Standard enum 0 / one / disabled |
| RX focal TOF / per-element gain | one zero / sixteen zeros | one zero / sixteen zeros |
| Emission / reception wedge delay | 0 / 0 us | 0 / 0 us |
| Pulser width | 0.5 us on all sixteen TX elements | 0.4999999987376214 us on all sixteen, matches float precision/tolerance |

Center delays, driver-version identity and physical geometry are not independently exposed/verified by this snapshot. MultiHW acquisition/start/decimation fields are correctly unavailable/not applicable in normal PA. The zero-law comparator uses existing 0.6-mm/5900-m/s geometry assumptions solely to compute zero delays; those are not parsed file values, newly detected probe specifications or physically verified mapping/material. PulserPowerMax=15.00 W; PulserPowerCurrent=0.00 W, read-only observation with acquisition OFF, not required candidate power.

Stage-2D production controller/state: initial Dirty/unverified -> connected Unknown -> applying Unknown/unverified -> Applied with readback_verified=true and header Config: Verified at matching draft/applied revision 10, applied_mode=current mode PA. Mode-specific PA snapshot from the owning worker is the same immutable object received by UI state. Requested scalar values/file path/hash/automatic-count behavior are separately retained from actual SI-unit snapshot. No mismatch was hidden. Actual UI readback text shows Start 0 us, Range 30 us, points 3001, sampling 100 MHz, representation enums 0/0/0, gains 20/0 dB, filter 1, TimeSlot 2600 us. PA configuration permission is distinct from acquisition support: hardware_modes remains FMC only; PA acquisition readiness false and Acquire disabled even after Verified. Generated Apply remains FMC-only; no acquisition button was invoked. Source assumptions and logical apertures do not establish physical probe identity/mapping.

Cleanup: explicit safety OFF calls succeeded before load, around reconnect, after load and before final disconnect. Final GUI Disconnect succeeded; handle destruction occurred on the serialized worker, backend device/acquisition references cleared, labels returned Disconnected/Unknown and readiness false. Normal window close completed shutdown_complete=true with no active operation. All 28 permitted API invocations succeeded on worker threads. The 50-ms main-thread heartbeat ran 95 times (maximum interval 0.511463 seconds includes initial scheduled delay); no responsiveness failure occurred. Script report passed=true, errors=[], vendor_dialogs=[], clean_close=true, protected_files_unchanged=true. Config/data SHA-256 inventory before/after matched exactly, including backup_original and all verified configurations. Device configuration is now the approved 16-RX 2600-us PA Compression candidate; acquisition was never enabled during this run. No attempt was made to restore a different configuration.

Files created: `oempa/verified_pa.py` (read-only exact-hash inspection of this specifically approved file), `tools/validate_phase5_stage2.py` (opt-in hardware-capable guarded acceptance tool), and five screenshots plus `artifacts/phase5_stage2/validation.json`. Files modified: `gui.py` (additive existing-file entry point and PA result presentation), `oempa/gui_backend.py` (existing-file load/verification and explicit FMC acquisition type guard), `ui/state.py` (separate configuration permission), `bridge/oempa_bridge.cpp` (one fail-closed MultiChannel getter return), `tests/test_ui_backend_offline.py`, `tests/test_ui_native_wrapper_offline.py`, and AGENTS.md. Native DLL/OBJ/LIB/EXP build artifacts regenerated. Existing file load mechanism, FMC writer/acquisition path, acquisition callbacks/storage, bridge signatures, driver/acquisition lifecycle, verified config bytes and saved arrays are preserved. No visible layout redesign or general PA writer/acquisition workflow added.

Validation after production changes: `cmd /c bridge\build_bridge.cmd` exit 0, known C4091/C4005 warnings only; Python py_compile passed for seven affected Python files. Explicit software-only commands `python -m unittest discover -s tests -p 'test_ui_*.py' -q` passed 110 and `python -m unittest discover -s tests -p 'test_tfm_offline.py' -q` passed 20, preserving all 124 baseline cases plus six new focused tests. New cases verify unchanged-file application without generated writer/acquisition, modified-file rejection before writing, enabled-MultiChannel precondition stop, mismatch retaining requested/actual without a retry, configuration-only PA state blocking acquisition, and fake-DLL MultiChannel read failure propagation. No hardware-capable test_ diagnostic/general discovery ran. Verified-readback screenshot visually reviewed; artifacts retain the exact live observations.

Next action: report Stage 2 and STOP. Do not acquire/reconnect/write again automatically. This validates full load and supported PA parameter readbacks, not physical acoustics, steering, MAX-buffer echo interpretation, required power estimation or resolution of the historic PA zero tail. Production PA acquisition remains unsupported; a future Stage-3 workflow and its precise settings must be reviewed and explicitly approved before any acquisition-enable call.

### Phase 5 Stage 2 pre-write inspection - 2026-10-08

Pre-execution implementation/validation: added pure hash-bound approved-file inspection, an additive adapter application method and GUI acceptance entry point, preserving the existing driver/AOS write/reconnect path and file bytes. State now distinguishes permitted configuration modes from supported acquisition modes; generated Apply and all acquisition remain FMC-only. Added checks for previously verified effective automatic 3001/256/100-MHz/8-bit output. A native readback defect discovered during inspection returned success/disabled when MultiChannel read/unlock failed; changed only that branch to return failure (no setter/parameter change). `cmd /c bridge\build_bridge.cmd` succeeded, with existing C4091/C4005 warnings only. Fake-DLL failure propagation and approved-file preservation/rejection/precondition/mismatch/configuration-only readiness tests pass. Latest restricted offline suite: 110 UI + 20 TFM = 130 passing, preserving the 124 baseline plus six focused cases. Seven affected Python files compile. The opt-in Stage-2 launcher permits exactly one unchanged-file load and documented read-only calls/OFF cleanup, blocks acquisition/callback preparation, monitors SDK modal dialogs and captures requested versus actual state/screenshots/checksums. Hardware execution is still pending; no result is presumed.

The user authorized Stage 2 only, applying the existing `configs/pa_test_0deg_timeslot_2600us_estimate.txt` with acquisition OFF. Read the entire checkpoint and inspected the file, GUI/adapter/state/verifier, established AOS loader and relevant vendor-source parser/write behavior. No Stage-2 hardware action has occurred at this checkpoint. File SHA-256 is `70a13245d7231d12b5f824965e6066918e8e61137f7575446c2699364239caa9`; do not modify or generate a replacement. Requested: one cycle; Start 0 us; Range 30 us; TimeSlot 2600 us; PointCount 0 automatic; Compression; Signed; analog/digital/beam gains 20/0/0 dB; filter 1; TX/RX logical aperture 0..15; 16 zero TX/RX delays and one RX law; Standard focusing; focal TOF 0; 16 RX gains 0; wedge/center delays 0; each TX width 0.5 us. No explicit bit-size/MultiChannel/DDF key. Existing acceptance expectation is 8-bit, 3001 points, 100 MHz, PointFactor 256, MultiChannel disabled and DDF disabled.

Vendor `UTKernel/UTCustomizedDriverAPI/CustomizedDriverAPI.cpp` initializes parsed MultiChannel false but writes EnableMultiHWChannel only when its saved-parameter bit is set. Thus the omitted key must not be claimed to force a previously enabled device OFF. Stage 1 read back disabled; Stage 2 must reread before write and stop if enabled. Standard focusing is passed to EnableDDF by the existing write path. No new hardware setter is appropriate. A narrow approved-file adapter/GUI entry point is being added because generated FMC Apply cannot apply this PA file. Separate configuration-mode permission from supported acquisition modes; do not enable PA acquisition. Hash checking, existing mode-specific verification, extra previously verified automatic-count/rate/factor/8-bit expectations, queued state/presentation and offline regression are required before execution. No default GUI setting is substituted for file values and no configuration file is written.

### Phase 5 Stage 1 completed - 2026-10-08

This is the active checkpoint. The user explicitly authorized controlled post-UI hardware acceptance, beginning with connection/readback/disconnect ONLY and stopping before Stage 2. Read this entire file and inspected the current launcher, GUI connection/event/close paths, controller, adapter, driver, acquisition constructor/stop, Python API and native connection/status/OFF exports before execution. Prior software-only checkpoints remain history; authorization extends only to this completed Stage 1. No configuration application/load/write, acquisition enable, callback registration/preparation, PA experiment, network change or native rebuild occurred.

Exact Stage-1 sequence: launch the production OEMPAGUI with its real adapter; observe disconnected/idle state and disabled Acquire/Stop; invoke its Connect button at fixed 192.168.1.11:5001; use the unchanged driver path (create handle, connect, acquisition OFF, cycle-count and MultiChannel getters); consume the worker result through the existing main-thread queue pump; observe live status and a two-second responsive connected interval; invoke the GUI Disconnect button; preserve existing acquisition-OFF cleanup, disconnect and handle destruction; observe disconnected state; request normal disconnected window close and wait for serialized cleanup. Configuration application and acquisition actions are guarded against accidental invocation in this acceptance launcher. No acquired dataset exists in this stage.

Created opt-in `tools/validate_phase5_stage1.py`; all Python API functions outside create_handle/destroy_handle/connect/disconnect/disable_acquisition/get_cycle_count/get_multichannel_state fail closed. The script checks the endpoint, records each call's result and worker ownership, asserts readiness remains false, checks initial/connected/disconnected labels, captures application-only screenshots and compares all files under configs/data by SHA-256 before/after. It has one connection attempt, no automatic retry or advancement to another stage; timeout/failure requests cooperative serialized cleanup instead of force-killing a worker. This is an explicitly hardware-capable tool and must not be included in offline test discovery.

Actual approved desktop command: `& '<python>' tools/validate_phase5_stage1.py`, outside the restricted sandbox because of the established Tcl initialization issue. Exit 0. Run timestamps UTC 2026-10-08T17:46:33.340606 through 17:46:39.387438. Live status returned connected true, endpoint 192.168.1.11:5001, CycleCount 1, MultiChannel supported true and enabled false. GUI displayed Connected / config unknown, cycles 1, Supported / Disabled; applied snapshot remained absent and Acquire disabled. Disconnect returned successfully, the handle was destroyed, device/acquisition references cleared, labels reset and normal close completed with shutdown_complete true and no owning operation. No callback errors or traceback. All nine API calls succeeded on worker threads: create, connect, OFF, cycle getter, MultiChannel getter, OFF, OFF, disconnect, destroy. No other Python device API was invoked.

Responsiveness: the main-thread 50-ms heartbeat ran 82 times during validation, including connection/cleanup and the connected hold. Maximum recorded interval was 0.500048 seconds, including the deliberately scheduled initial 500-ms delay; this is an observed short-run measurement, not a real-time guarantee. Connected screenshot visually reviewed: endpoint/state/readbacks and disabled Acquire/Stop are visible without clipping or overlap. Apply is ordinarily available while connected, but guarded from writing during this run. No production UI/controller/backend/bridge fix was necessary. Three PNGs and validation.json are under `artifacts/phase5_stage1`; report passed=true, errors=[], clean_close=true, protected_files_unchanged=true.

Readback limits: identity/firmware/serial are explicitly unavailable in this UI and were not newly read or inferred from historic values. This stage exercised existing topology/status getters, not full acquisition-parameter verification. The native MultiChannel getter can return enabled=false when its enable-state read/unlock fails; the logged false is its returned value and is not a new independent verification of that field. Full mode-aware readback remains Stage 2. No physical probe/channel mapping or acoustic claim is made.

Regression commands restricted to previously inspected offline patterns: `python -m unittest discover -s tests -p 'test_ui_*.py' -q` passed 104; `python -m unittest discover -s tests -p 'test_tfm_offline.py' -q` passed 20, preserving the 124-test baseline. `python -m py_compile tools/validate_phase5_stage1.py` passed. No hardware-capable test_ diagnostic or general discovery was run. Files created: Stage-1 launcher and four review artifacts. File modified: AGENTS.md only. All production code, verified configurations (including backup_original), saved arrays and Windows/Ethernet configuration remain unchanged.

Next action: report Stage 1 and STOP. Stage 2 needs a separate instruction; do not reconnect/apply automatically. Before Stage 2 choose an existing verified configuration and review how to apply it through the production adapter without substituting GUI defaults or modifying the verified file. Unexpected requested/actual differences must stop the stage. Standalone hardware A-scan is not currently enabled by the production adapter (A-scan tab displays selected FMC traces); resolve the exact supported Stage-3 workflow before requesting physical acquisition approval rather than silently substituting FMC or PA. Stages 3 and 4 each require their own explicit approval before enabling acquisition. Later diagonal B-scan and TFM use the same captured cube offline, with explicit TFM geometry/timing assumptions and unverified mapping.

### Phase 4 completed - 2026-10-08

This is the active checkpoint. The user explicitly approved offline TFM implementation and UI integration from existing FMC data. Phase 4 is complete; stop here. Previous stop-before-TFM/Phase-4 text is preserved as history and superseded only by this authorized offline scope. No OEM-PA connection, handle creation, device read/write, acquisition enable, PA diagnostic, network change, native build or verified-configuration modification occurred.

Implementation and mathematical model:
- Created `oempa/tfm.py`, a pure NumPy backend with no Tk/SDK/device import. Frozen `LinearGeometry`, `ImageGrid`, `TimingAssumption`, `TFMRequest`, `TFMResult` and `TFMDisplay` distinguish acquired provenance, requested modeling assumptions, raw image and derived display. Source remains `FMC[TX,RX,sample]`; the initial model requires a nonempty square cube and geometry element count matching both matrix axes. Coordinates are centered `(index - (count-1)/2) * pitch` on z=0; element count is derived from source dimensions, not a probe-identity constant. Physical ordering is explicitly assumed and unverified; result mapping_verified remains false even if unrelated source metadata is marked verified, because this model does not consume a verified physical mapping.
- All backend geometry/time quantities use metres/seconds. For each grid point, one-way element times are `hypot(x-element_x,z)/velocity`, paired time is their TX/RX sum, and sample coordinate is `(paired_time-start_s)*sampling_hz`. Raw TFM is the equally weighted coherent sum of all TX/RX samples in float64, not divided by pair count and not a sum of absolute per-trace samples. The simple model assumes homogeneous longitudinal-wave propagation and point elements, with no wedge/refraction, focal/wedge/electronic delay correction, attenuation/directivity weighting, mode conversion, apodization, Hilbert envelope or physical calibration. Callback MAX output is not claimed to be pre-compression RF.
- Nearest uses `floor(sample_position+0.5)` (ties upward). Optional linear interpolates neighboring samples, including the exact last acquired sample. Positions outside `[0,N-1]` contribute zero before index clipping; there is no nearest extrapolation or array wraparound. Finite positive pitch/velocity/rate, finite start, real finite data, TX/RX/sample axes, consistent shape/dtype, increasing finite grid limits, depth >=0, integer counts >=2 and method are checked before reconstruction. Shared captured cycle count/start/rate/sample count are verified against source dimensions; missing or differing per-cycle timing is rejected.
- Complete acquisition metadata is authoritative and cannot be overridden by assumed timing. Incomplete/legacy metadata requires explicit rate AND start supplied separately as TimingAssumption; the original AcquisitionMetadata is retained unchanged, with unknown hardware/revision still unknown. No constructor defaults, current GUI range/settings, 100-MHz/zero-start/3001 constants or waveform-derived inference are used by the TFM backend/UI. Result includes source metadata/label, source configuration revision, reconstruction request, actual-or-assumed timing and origin, element coordinates, method, UTC reconstruction timestamp and unverified-mapping/model/buffer warnings. Result/image/coordinate arrays are readonly by default.
- Raw signed sum is separate from absolute, normalized magnitude and dB views. Normalized magnitude is `abs(I)/max(abs(I))`; dB is `20*log10(abs(I)/peak)` with a documented default -60-dB floor. All-zero normalized images remain zero and dB images are entirely the floor, without divide-by-zero/NaN. These are magnitudes of the coherent sum, not analytic-signal envelopes; display changes do not change raw data.

UI/controller:
- Created `ui/tfm_workspace.py` to replace the TFM placeholder with Open FMC .npy / Use current FMC, blank pitch/velocity, explicit legacy-rate/start fields, x/depth bounds and pixel counts, nearest/linear selection, raw/absolute/normalized/dB display and Reconstruct offline. Complete captured timing appears in source text and legacy override controls are disabled. UI coordinates are mm and entered timing MHz/microseconds, converted to SI for requests. Image uses physical x/z coordinates, inverted depth, equal physical aspect and a colorbar referenced to image peak for dB. Source/result provenance and Probe/channel mapping: Unverified stay visible; reconstructed features are explicitly not identified as defects.
- TFM has separate source/request/result revisions and does not overwrite current acquired FMC or its hardware revision. Assumption/source edits preserve the old image/provenance and label it STALE; display-mode changes do not stale the raw result. A historical current-acquisition source is identified when hardware draft/current dataset changes. Legacy FMC constructor timing defaults are deliberately ignored; Use current FMC without metadata requires the same explicit assumptions as a legacy file.
- Added generic `loading` / `reconstructing` operations to `ui/state.py`, using the unchanged OperationController single-owner queue/worker lifecycle. These work while disconnected and do not require hardware apply. Offline errors preserve the last verified hardware configuration/readback rather than pretending an image failure partially wrote the device; error still blocks acquisition until resolved. Source loading and reconstruction use the owning worker, with cancellation checks before/after file load and within reconstruction chunks/TX loops. Workers emit only queued progress/results; Tk variables/widgets and Matplotlib are used solely on the main thread. Stop, operation locking and close-after-owning-worker cleanup remain intact.
- Real-window inspection found insufficient plot space with all TFM settings expanded at minimum size and an overlong colorbar/stale title. Settings are now collapsible and collapse after successful reconstruction; source/display/provenance remain visible. Compact colorbar labels and a two-line stale title retain readable axes/units. No other interface redesign or hardware workflow changes were made.

Validation and saved-data results:
- Created `tests/tfm_synthetic.py` exclusively for deterministic synthetic point-reflector impulses. It is separate from acquisition and uses independent scalar travel-time calculations. Created `tests/test_tfm_offline.py`: all 20 cases pass. Nearest reconstructions focus centered/off-axis known reflectors at the expected grid point (within 0.1 mm) with all 64 pair impulses summed for an 8-element model. Tests cover 25/40-MHz timing, nonzero 2-microsecond start, 0.6/0.9-mm pitch, linear localization and analytic ramp interpolation, half-up rounding, strict outside-window zeros, last/one-sample endpoints, invalid geometry/grid/velocity/rate/axes/dimensions/method/samples, consistent readback, immutable original metadata, int8 sum without overflow, exact 20-log dB reference, zero-safe display, progress, mid-reconstruction cancellation and chunk invariance.
- Created `tests/test_ui_tfm_offline.py`: 12 new fake-Tk/fake-adapter cases pass, with real Matplotlib figures. They cover construction, no-source/invalid readiness, worker file loading, explicit legacy assumptions, authoritative captured timing, offline operation/locking/progress, display/colorbar/equal-aspect physical axes, stale assumptions/source replacements, current-FMC provenance, preservation of hardware truth on offline errors, serialized ownership, cancellation and close cleanup. Preserved all 92 existing test cases; the obsolete Phase-3 placeholder expectation now checks the authorized offline workspace and disabled initial reconstruction. Final `python -m unittest discover -s tests -p 'test_ui_*.py' -q` passed 104 tests; separate `python -m unittest discover -s tests -p 'test_tfm_offline.py' -q` passed 20, for 124 passing software-only cases. No general test discovery/hardware-capable test was run.
- Only after initial synthetic validation passed, loaded and reconstructed existing `data/fmc16x16.npy` offline. It remains (16,16,3001), int8, metadata-incomplete with no timing sidecar. Saved-data diagnostic examples explicitly supplied pitch 0.6 mm, velocity 5900 m/s, rate 100 MHz and start 0 microseconds as modeling/timing assumptions, not newly verified physical facts or UI defaults. Its original SHA-256 is still `ad7db22cd9532ded625f8ae401d7cf72d8a715327c42f6fb1cd28b57841bf4fe`; no metadata was fabricated or written into this source. Nearest and linear 201x201 examples took approximately 0.104 and 0.178 seconds respectively on this machine (single observations, not a benchmark guarantee). No image feature is interpreted as an acoustic reflector/defect.
- Created `tools/reconstruct_tfm_offline.py` with caller-required pitch/velocity and explicit legacy-rate/start arguments. Commands run: `python tools/reconstruct_tfm_offline.py data/fmc16x16.npy --pitch-mm 0.6 --velocity-m-s 5900 --legacy-rate-mhz 100 --legacy-start-us 0 --method nearest --output artifacts/phase4_tfm/nearest`, and the same with `--method linear --output artifacts/phase4_tfm/linear`. Both exited 0. Each output contains raw numeric tfm_raw.npz, full source/request provenance.json and a labeled experimental PNG; no source/verified configuration is modified.
- Created opt-in `tools/validate_phase4_window.py`, which replaces the adapter with an offline-only stub before GUI import and asserts no oempa.api/driver import. Approved desktop execution was needed due to the previously established restricted-sandbox Tcl issue; no environment repair/path workaround was added. `python tools/validate_phase4_window.py data/fmc16x16.npy --pitch-mm 0.6 --velocity-m-s 5900 --legacy-rate-mhz 100 --legacy-start-us 0` exited 0 after final layout fixes: real empty/load/reconstruct/absolute/dB/stale views, 1300x820 and 1100x700 windows, disabled disconnected Acquire, no callback errors, no geometry-boundary issues, SDK not loaded, clean serialized close. Five application-only screenshots and validation.json are in `artifacts/phase4_window`; screenshots were visually reviewed. Interim minimum-size layout warning/clipping was fixed; final runs reported no warning/traceback. This is not hardware acceptance.
- Final py_compile, AST/compile/whitespace checks passed for all 12 new/modified Python files; fresh imaging/UI imports loaded no device modules. Static checks confirmed no prohibited device APIs or fixed acquisition timing/count assumptions in the TFM backend/view. FMC source checksum was rechecked unchanged.

Files created: `oempa/tfm.py`, `ui/tfm_workspace.py`, `tests/tfm_synthetic.py`, `tests/test_tfm_offline.py`, `tests/test_ui_tfm_offline.py`, `tools/reconstruct_tfm_offline.py`, `tools/validate_phase4_window.py`, and the above review artifacts. Files modified: `gui.py` (event/presentation hooks only), `ui/state.py`, `ui/workspace.py`, `tests/test_ui_phase3.py` (same existing cases, updated placeholder assertion and fake pack_forget capability), `tools/validate_phase3_window.py` (obsolete placeholder assertion), and AGENTS.md. The controller implementation, existing acquisition/driver/configuration/dataset/FMC/B-scan backend and bridge APIs/code, backup_original, all PA experiment configurations, network and saved acquisition arrays were not changed.

Performance/physical limits: CPU NumPy only, no new GPU/CUDA/dependency. Complexity is O(TX*RX*image pixels); default 1024-point chunks bound temporary pair buffers and preserve cancellation boundaries. Grid limit is 1,000,000 points; very large cubes/element counts can still take substantial time/memory. File reads and finite-data validation are not interruptible mid-call, so cooperative close waits for them to finish; there is no force-kill. Only square arrays and a shared output time axis are supported, without resampling. Physical probe identity/channel mapping, pitch, material/specimen/wedge geometry, actual legacy timing, waveform coherence/MAX versus RF meaning, system delays and physical acoustic validity remain unverified. No PA sector scanning, hardware experiments or automatic acceptance is added.

Next action: report Phase 4 and stop. Hardware acceptance, physical validation and further phases require a separate explicit request.

### Phase 4 implementation in progress - 2026-10-08

The user explicitly authorized offline TFM from existing FMC data; prior stop-before-Phase-4 instructions are superseded only for this offline task. Hardware/network/configuration constraints and all history remain unchanged. Read the latest checkpoints, dataset/FMC/controller/view interfaces and saved FMC. `data/fmc16x16.npy` is shape (16,16,3001), int8, with no timing sidecar; load_dataset correctly reports incomplete metadata and unknown timing. Its SHA-256 before work is ad7db22cd9532ded625f8ae401d7cf72d8a715327c42f6fb1cd28b57841bf4fe. Legacy reconstruction requires explicit rate AND start assumptions, stored separately from original metadata; geometry/material are always assumptions, mapping remains unverified.

Initial mathematical milestone: created pure oempa/tfm.py and separate synthetic-only tests/tfm_synthetic.py. Conventional homogeneous direct-contact linear-array coherent sum uses (distance_TX + distance_RX)/velocity and (time-start)*rate. Implemented nearest (half-up), optional linear, strict zero contribution outside [0,N-1], float64 accumulation, bounded chunked NumPy and cancellation/progress hooks; no device/Tk imports. 17 dedicated synthetic/math/provenance/display tests passed, including centered/off-axis point-reflector localization, 25/40-MHz sampling, nonzero start, varied pitch, invalid grids/velocity/geometry, endpoint/interpolation and signed-sum overflow behavior. This validates mathematical assumptions, not physical probe/specimen facts. Backend acquisition, bridge, verified configs and saved data are untouched. The UI now owns a separate TFM source/result state and serialized loading/reconstructing operations; offline errors preserve hardware readback truth. Existing 92 tests passed after integration (only obsolete placeholder expectation updated to the authorized TFM workspace). Further offline GUI/cancellation/real-window and saved-data checks remain before completion; do not start hardware acceptance.


### Phase-3 real-window validation completed - 2026-10-08

This is the active checkpoint. The user approved Phase 3 and authorized only local Tk/Tcl diagnosis and disconnected real-window validation before Phase 4. Completed and stopped; no Phase 4/TFM/hardware acceptance work is authorized by this checkpoint.

Root cause / correction to earlier findings: the specified Python is 3.14.7 x64, executable/prefix/base_prefix all `<Python installation>`. `_tkinter` imports from that installation's DLLs directory and reports Tcl/Tk 9.0. TCL_LIBRARY and TK_LIBRARY are unset. No external tcl directory exists, but none is required: Python zipfile inspection confirms tcl90.dll (3,383,352 bytes) contains 839 entries including tcl_library/init.tcl; tcl9tk90.dll (2,152,408 bytes) contains 90 entries including tk_library/tk.tcl. Approved unsandboxed Tk creation reports Tcl/Tk 9.0.4 and embedded zipfs libraries `//zipfs:/lib/tcl/tcl_library` and `//zipfs:/lib/tk/tk_library`; zipfs mount sources are this installation's DLLs. Restricted execution reproduces init.tcl failure while approved desktop execution succeeds. This establishes an execution-environment/sandbox-specific Tcl initialization failure, not project code failure, incomplete Python installation, or TCL_LIBRARY/TK_LIBRARY mismatch. The exact underlying sandbox/zipfs interaction has not been established. No repair/reinstall or smallest-component installation is required. No software was installed, environment variables changed, runtime extracted, or machine-specific Tcl path added to the application. Run desktop validation/GUI outside the restricted tool sandbox with the specified Python.

Diagnostics: approved `& '<python>' -m tkinter` opened successfully and the demo process exited with code 0. Separate approved probes created/destroyed Tk and reported the above runtime/mount paths. The earlier Phase-3 checkpoint's assertion that a matching runtime was missing is superseded by this evidence; its historical record remains intact below.

Real-window validation: created opt-in `tools/validate_phase3_window.py`, which imports the actual OEM-PA GUI and adapter, replaces all Python device API functions with fail-closed guards before GUI construction, and never connects or creates a device handle. The SDK DLL is imported through the existing application path; no SDK/device function is invoked. This validates the real Tk/ttk/Matplotlib composition rather than widget fakes. The script captures only the application window, records callback errors and mapped-widget parent-boundary checks, exercises disconnected tab/mode/PA controls and requests the actual cooperative controller close. No verified configuration/dataset file is written.

Approved command `& '<python>' tools/validate_phase3_window.py` completed with exit 0 after fixes. Main window, all four setup sections and five display tabs rendered; geometry tested at 1300x820, 1100x700 and 1600x1000 (28 layout observations including calculated PA at minimum size). Disconnected/idle/dirty/no-data state is visible; Apply/Acquire/Stop disabled, endpoint readonly. TFM placeholder visible. Actual offline PA button produced 16-element separately quantized TX/RX delay curves using explicitly assumed 0.6-mm pitch, 5900-m/s velocity and 30-degree angle, with no physical steering/mapping claim. Cleanup through on_close, serialized worker and Tk event pump completed, state.shutdown_complete true, no remaining operation, window destroyed. Final report: errors [], geometry-boundary issues 0, hardware_api_calls [], clean_close true. Screenshots were visually inspected; these checks do not claim hardware/acoustic acceptance or exhaustive DPI/theme testing.

Genuine UI issues discovered/fixed only: PA summary printed full float arrays causing clipped text at minimum size; replaced with compact formatted delay spans (TX 0.764 / RX 0.765 microseconds for preview) and bounded summary wrapping. Existing corrupted literal question-mark unit/degree/stale labels in gui.py corrected to proper Unicode. Persistent Matplotlib tight-layout engines now recalculate margins on resize, keeping axis labels visible in the short minimum-size PA plot. No interface redesign, hardware/backend/bridge/configuration logic changes or TFM implementation. The first validation run encountered Tcl_Obj JSON report serialization; corrected only the validation script's string conversion and reran successfully.

Files created: `tools/validate_phase3_window.py` and six PNG screenshots plus `artifacts/phase3_window/validation.json`. Files modified: `gui.py`, `ui/workspace.py`, `tests/test_ui_phase3.py` (strengthened existing preview summary assertion), and AGENTS.md. All safety constraints, backend diagnostic history, configs/backup_original.txt, verified experimental configs, network and saved acquisition data remain unchanged.

Final validation: explicitly safe `& '<python>' -m unittest discover -s tests -p 'test_ui_*.py' -q` passed all 92 existing tests after the UI fixes. No hardware-capable test outside that inspected pattern was run. `python -m py_compile gui.py ui/workspace.py tools/validate_phase3_window.py tests/test_ui_phase3.py` passed; AST/whitespace checks passed for all four changed Python files. Real-window validation independently exited 0 with no tracebacks/callback errors. Screenshots: device_ascan.png, probe_fmc.png, acquisition_bscan.png, pa_preview.png, pa_preview_minimum.png, tfm_minimum.png under artifacts/phase3_window; validation.json records actual runtime and measurements.

Next action: report results and stop after Phase-3 visual validation. Do not implement TFM, enter Phase 4, or run hardware/network/configuration work automatically.


### Phase-3 real-window validation in progress - 2026-10-08

Authorized scope: diagnose Tk/Tcl and validate the disconnected real window only; no Phase 4 or hardware/network/configuration changes. Initial sandbox execution reproduces init.tcl failure with Python 3.14.7, matching prefix/base_prefix, _tkinter and Tcl/Tk 9.0 DLLs, unset TCL_LIBRARY/TK_LIBRARY, and no external tcl directory. Approved unsandboxed `python -m tkinter` launches successfully. A separate approved probe creates/destroys Tk and reports Tcl/Tk 9.0.4, Tcl library `//zipfs:/lib/tcl/tcl_library`, Tk library `//zipfs:/lib/tk/tk_library`; zipfs mounts point to this Python installation's DLLs. Python zipfile inspection confirms both DLLs contain the matching runtime scripts (including init.tcl/tk.tcl). Therefore the earlier missing-runtime conclusion was incorrect: this is a sandbox-specific initialization failure, not an incomplete installation or environment-variable mismatch. No repair/reinstall, environment edits or application Tcl path workaround is necessary. Exact sandbox/zipfs failure mechanism is not established. Next: approved desktop UI validation without connecting, creating device handles or invoking hardware APIs.


### Phase 3 completed ? 2026-10-08

This is the active checkpoint. The user approved Phase 2 and explicitly authorized production layout/workflow implementation with software-only validation. Phase 3 is complete; stop here. Phase 4 and hardware acceptance require a separate request. No OEM-PA connection, configuration load/write, acquisition enable, network change, SDK build, or PA/FMC hardware experiment occurred.

Files created: `ui/layout.py`, `ui/setup_panel.py`, `ui/workspace.py`, `ui/presentation.py`, `tests/test_ui_phase3.py`. Files modified: `gui.py`, `ui/state.py`, and this checkpoint. The existing widget-construction block was extracted/replaced while preserving OEMPAGUI/run_gui, controller event handling, backend APIs, FMC mapping, processing and persistence. Backend/bridge/configuration/data files were not edited; backup_original and all experimental configurations remain untouched.

Layout: persistent title and endpoint/connection/operation/configuration/dataset state; left Device/Probe/Acquisition/Mode Settings notebook; right A-scan/FMC/B-scan/Phased Array/TFM notebook; persistent Apply/Acquire FMC/Stop/Save, received-cycle progress, short status/error/mismatch area and log. Device endpoint is readonly. Probe inputs start blank and are explicitly user assumptions, with unknown identity/unverified mapping. These placeholders do not affect the hardware configuration or establish physical provenance. Acquisition shows editable supported FMC requests separately from last-observed readonly start/range/count/rate/encoding/gains/filter/TimeSlot. Missing information remains unavailable. Hardware identity/firmware extensions were not added.

State adds configurable supported hardware modes, apply readiness and presentation properties. The GUI enables only the established FMC adapter; A-scan mode is offline viewing and PA mode is offline preview. Unsupported mode Apply is blocked in state.begin, including direct controller submissions, and acquisition readiness requires a supported mode plus the existing connected/applied/verified matching revision. Mode changes dirty configuration and stale datasets; display tab, selector, gates and preview assumptions do not submit device operations. All setup/preview controls lock while an operation owns the controller. Stop signals cooperative cancellation; safe close, queued main-thread consumption and serialized cleanup remain unchanged.

A-scan/FMC retain actual recorded axes, selectors, separate Matplotlib canvases and pan/zoom/reset toolbars. Metadata summaries derive mode/shape/rate/range/revision from immutable dataset metadata; legacy timing remains incomplete. Stale historical data remains available with explicit STALE wording and existing stale plot titles. B-scan retains RF/Absolute software gates and visibly labels the FMC pulse-echo diagonal as not mechanically scanned; MAX-buffer provenance is explicit. PA calculation uses the unchanged backend FocalLawCalculator for assumed pitch/velocity, logical aperture/angle and separately quantized TX/RX delay plots/summary. Pitch/velocity begin blank; edits invalidate calculated laws. Physical steering/mapping and PA receive zero-tail findings remain unverified. No PA apply/acquire, linear/sector scan or TFM implementation exists. TFM is a placeholder. Ordinary controller errors/mismatches appear inline and in the log, preserving requested versus observed values; close acknowledgement remains a dialog. Complete AOS warning-stream capture remains deferred.

Software-only validation:
- Explicitly restricted test discovery to inspected `test_ui_*.py`: pure state/controller/readback/metadata tests, fake API/DLL/backend tests and headless GUI tests. No other hardware-capable diagnostic was run.
- Original 84 tests passed after extraction. Final command: `& '<python>' -m unittest discover -s tests -p 'test_ui_*.py' -q` passed all 92 tests (84 preserved plus 8 Phase-3 cases).
- New tests exercise complete layout construction using widget fakes that reject mixed grid/pack children, real Matplotlib figures, mode/state/control presentation, unsupported hardware submissions, 25-MHz axes, TX/RX waveform selection, B-scan controls, PA preview and invalidation, operation locking, Stop and close delegation. Earlier regression tests continue to exercise asynchronous worker/error/cancellation/close cleanup.
- Python stdin compile/AST/whitespace checks passed for gui.py, main.py, all ui modules and the new test (10 files); module import checks confirmed UI modules load neither oempa.api nor oempa.driver; forbidden device-operation tokens are absent from ui modules.
- Attempted withdrawn real-widget validation failed before window construction because this Python installation lacks usable Tcl 9 init.tcl. No SDK/device was loaded. Tests were changed to geometry-checking widget fakes rather than skipped; all 92 passed. No screenshot or real-window visual acceptance is claimed. A usable matching Tcl/Tk installation is required for later visual acceptance; no environment package was installed/changed.

Next action: report Phase 3 and stop. Separately authorize future visual/hardware acceptance. Standalone/live A-scan, PA hardware operations, probe-profile persistence/physical verification, dataset Open workflow, firmware/capability extensions, AOS warning notifications, linear/sector scanning and TFM remain deferred.


### Phase 2 completed — 2026-10-08

This is the active checkpoint. The user approved Phase 1 and authorized Phase 2 software-only implementation: aggregated readback, mode-aware verification, actual timing, and dataset metadata/persistence. Stop after Phase 2; Phase 3 and hardware acceptance require separate authorization. No device connection, configuration load/write, acquisition enable, network change, real GUI launch, or PA diagnostic occurred during this phase.

SDK discovery: `CustomizedDriverAPI.cpp` uses `GetMultiHWChannelAcqWriteStart` and `GetMultiHWChannelAcqDecimation` for FMC readback, and does not use normal `GetAscanStart` for that path. Its file serialization scales the start array by 1e6 to microseconds, establishing seconds internally. The write path clears the replay TX aperture, selects one RX, copies hardware-cycle starts for replay, and sets range/count/factor separately. These distinctions now drive FMC aggregation and verification rather than treating replay as normal PA.

Implementation:
- Created `oempa/hardware_state.py`: frozen cycle/hardware snapshots in SI units, explicit `None` for unavailable/not-read fields, getter errors, field-level verification reports, and an explicit standalone `AscanRequest` verification schema. Snapshots include topology, timing/count/factor/rate, encoding/compression, gains/filter/TimeSlot, apertures, widths/TX delays, MultiHWChannel starts/packed decimation/acquisition flags, and PA receive delays/focusing/DDF/focal TOF/gains/wedge delays where applicable.
- FMC verification checks all cycles, selected RX, hardware/replay ordering, TX aperture on hardware cycles and empty TX on replay, requested acquisition/common settings, pulser widths/zero TX delays on hardware cycles, and common output timing/encoding. Replay does not require absent TX or PA receive-law fields. Automatic point count/factor/rate are validated as readback, not compared with invented constants. PA verification instead checks the normal one-law apertures, quantized TX/RX delays, Standard/DDF state, and receiver-law fields. Standalone A-scan verification accepts an explicit request including start and encoding; no new A-scan or PA hardware writer/workflow is enabled.
- Extended `bridge/oempa_bridge.h/.cpp` and `oempa/api.py` with one additive read-only export: SDK emission widths/TX delays and MultiHWChannel acquisition flag/start-array/packed-decimation readback. Replay TX fields are explicitly not read (`-1` native count -> Python `None`). Existing acquisition callbacks, storage, setters, exports, and FMC configuration generation are unchanged. Created `bridge/build_bridge.cmd`; rebuilt DLL/import-library/object/export artifacts successfully using the established VS/AOS build recipe. The DLL was not loaded or called against hardware.
- `oempa/gui_backend.py` now requires mode-aware parameter verification after load/reconnect and refreshes readbacks with acquisition OFF before a future FMC acquisition. Mismatch prevents starting, preserves actual values/report, and does not overwrite requested values. Callback point count/size/sign/bit size must match captured readback. The processor receives actual start/rate, preserving `(TX,RX,N)` and cycle mapping.
- `ui/state.py`/`controller.py` retain actual snapshot, immutable requested values, mismatch fields, and operation revision through queued success/errors. The Phase-1 thread ownership, cancellation, close, dirty/applied/stale readiness rules remain intact. Actual snapshot means last observed readback; disconnect/failure clears applied readiness rather than claiming that observation is current verified hardware truth.
- Created `oempa/dataset.py`: frozen metadata with UTC timestamp, revision, mode, shape/dtype/axis names, full actual per-cycle snapshot, separate requested parameters/focal-law assumptions, callback representation/MAX-buffer source, and explicit unknown/unverified probe identity/mapping. Time axes use `(start_s + n / sampling_hz) * 1e6`; old data cannot adopt later draft values.
- Persistence uses `.npy` plus `.npy.json` with schema version and SHA-256 binding to the array file. Each file uses temporary-write/atomic replacement; a crash between replacements is detected by hash mismatch. Missing/malformed/mismatched sidecars load the array as metadata-incomplete with sample indices, never assumed timing. Shape/dtype, axes/cycle count, common timing/encoding, and callback/readback representation are validated on load. No pickle loading. Metadata-free overwrites explicitly invalidate old sidecars even for byte-identical arrays.
- `FMCData` retains existing constructor/processor interfaces and supports optional metadata and `load`; metadata-backed save persists sidecars. Explicit old constructor timing remains compatible, but GUI-created acquisitions and legacy loading do not use its historical defaults. `gui.py` keeps its layout, logs actual timing and mismatches, uses dataset axes, preserves stale labels, saves metadata, and labels legacy views with sample indices. Legacy B-scan time gates are not applied as microseconds. Amplitude-limit reporting follows the actual integer dtype; gain is not changed.

Software-only validation:
- Preserved all 49 Phase-1 cases; three backend fixtures were upgraded from topology-only `SimpleNamespace`/mock readbacks to complete fake FMC readbacks, retaining their original assertions and purpose.
- Created `tests/ui_readback_fakes.py`, `tests/test_ui_phase2.py`, and `tests/test_ui_native_wrapper_offline.py`; extended backend/GUI offline tests. Native wrapper tests substitute a fake DLL loader/API (no real SDK/device load), check the 216-byte extended struct layout, count guards, real zero versus replay not-read, and start-array decoding. Synthetic tests cover matching/mismatching/missing readbacks, multiple mismatches, PA versus FMC requirements, nonzero A-scan start, 25/50-MHz axes, stale metadata, FMC/PA/A-scan provenance round trips, legacy/corrupt sidecars, external changes blocked before acquisition, and GUI plot/save behavior. Temporary folders only are used for test saves.
- `& '<python>' -m unittest discover -s tests -p 'test_ui_*.py' -q` passed 84 tests. Earlier intermediate runs passed 72 and 78 tests. No existing hardware-capable diagnostic was run.
- `cmd /c bridge\build_bridge.cmd` completed compilation/linking with exit 0, including after replay-read handling was refined. Only SDK C4091 and the existing duplicate-export-macro C4005 warnings occurred; no errors.
- Final `python -m py_compile` and AST/whitespace checks passed for 14 UI/backend/test files. Pure imports of state/controller/readback/metadata/FMC confirmed no `oempa.api` or `oempa.driver` load. Static checks confirmed no fixed 100-MHz/zero-start/3001-point assumptions remain in the GUI acquisition adapter and the new native export contains readbacks only. Fake-DLL wrapper tests cover API import/decoding without loading the SDK. The final full offline suite rerun passed all 84 tests.

Limitations/deferred work: no hardware readback or acoustic acceptance has been performed, so the new getter/verification path is compile-checked and fake-tested rather than device-verified. The initially supported FMC cube requires consistent per-cycle output timing and zero raw MultiHWChannel decimation; differing starts/rates/nonzero decimation block acquisition rather than being guessed/resampled. Automatic point-count/factor/frequency have no user-requested constants; their actual values and consistency are verified. Metadata indicates software/readback provenance, not physical pulse count, frame coherence, pre-compression RF, required pulser power, or physical steering/echo validity. Probe identity/mapping remain unknown; PA zero-tail findings remain unresolved. No production redesign, new mode controls, sector/linear scanning, TFM, scanner work, AOS warning stream, or pulser-power estimator was added. Existing config files (especially `backup_original.txt` and all verified 2600-us PA candidates), saved data, driver/acquisition lifecycle code from Phase 1, focal-law calculation, and configuration builders were not changed. Loading is available through backend dataset/FMC interfaces; a visible Open workflow is deferred to UI work.

Next action: report Phase 2 results and stop; do not begin Phase 3 or run hardware acceptance automatically.

### Phase 1 completed — 2026-10-08

This is the active UI checkpoint. The user approved the architecture and authorized only Phase 1 implementation and software-only validation. Stop after Phase 1; do not automatically implement Phase 2 or run hardware acceptance. All PA findings and hardware/network safety constraints below remain in force.

Created `ui/__init__.py`, `ui/state.py`, and `ui/controller.py`. The state tracks connection/operation, draft/applied revisions, validity, readback verification and its scope, acquisition mode, dataset freshness, closing, status, and errors. Readiness requires connected/idle, valid/applied/verified matching revision and mode, no error, and no pending close. Editing invalidates current dataset freshness without changing the historical applied revision; failed/partial apply forgets applied hardware truth. Only the controller's creating/main thread may submit, cancel, request shutdown, or consume events.

The controller runs one non-daemon worker at a time and retains ownership until that worker has exited and its terminal event is consumed. Workers emit structured progress/completed/cancelled/error events through `queue.Queue`; operation IDs reject stale events. The GUI's main-thread `root.after` pump updates state/widgets. Workers never call Tk, including `after`. Closing rejects commands, requests cooperative cancellation, and schedules backend cleanup only after the prior worker releases ownership. Cleanup failure leaves the window open with an error and permits a close retry; no worker is force-killed and no Tk-thread join blocks the window.

Added `oempa/gui_backend.py` as a narrow worker-owned adapter around existing FMC operations, retaining the existing configuration builder, acquisition/replay path, processor, and reconnect behavior. `gui.py` keeps its visible layout, entry points, A-scan/FMC/B-scan plots, software gates, progress, and save path; obsolete GUI worker methods were replaced by controller submissions. Draft variables are captured on the main thread, entries lock during operations, acquisition remains blocked after connect until apply succeeds, dirty/stale/error state is visible, historical plots are marked stale, and display exceptions do not terminate the event pump. The established endpoint is fixed in readonly controls.

Localized backend safety changes: `OEMPAAcquisition.acquire` has an optional trailing `cancel_event` argument; the existing default call path remains available. Cancellation checks occur before preparation/start and in the polling loop; cancellation still executes the existing `finally: stop()`, and stop failure is an error rather than successful cancellation. The native callback and storage code are untouched. `OEMPADevice.connect` and configuration reconnect failure paths now attempt disconnect even after a partial connect failure; disconnect failure retains the handle for retry rather than permitting destruction of a potentially live connection. These paths were exercised with a fake Python API only.

Verification scope is intentionally limited in Phase 1: the real GUI adapter marks successful full load/reconnect plus the existing cycle-count/MultiChannel-support/enabled readbacks as basic topology verification and logs that exact scope. It does not claim full parameter, pulser-power, probe, acoustic, or physical validation. Full configuration readback and actual timing are Phase 2; the existing FMC processor timing assumptions remain explicitly deferred rather than silently presented as newly verified hardware readback. No new PA control, TFM, scanner workflow, service-wide metadata system, or AOS warning hook was implemented.

Offline tests created and inspected before execution:
- `tests/test_ui_phase1.py`: pure state/controller/fake tasks; no OEM-PA imports.
- `tests/test_ui_backend_offline.py`: loads backend source against a fake `oempa.api` module; no native DLL loading, real device calls, or configuration writes. Tests cancellation, normal-path compatibility, partial connection/reconnect failure, topology-readback failure, and cleanup errors.
- `tests/test_ui_gui_offline.py`: imports the GUI against a fake adapter; uses fake Tk variables/root, mocked widgets, and synthetic NumPy FMC data. No Tk window is opened. Checks main-thread access, draft locking, readiness, stale A-scan/B-scan views, event-pump recovery, and close/retry behavior.

Validation completed: `& '<python>' -m unittest discover -s tests -p 'test_ui_*.py' -v` passed all 49 tests. An earlier integration run exposed a missing stale A-scan title; that was corrected and included in the passing suite. `python -m py_compile` passed for all 10 new/changed Python files and the unchanged launcher (11 files total). A Python stdin check using `ast.parse`/`compile` and whitespace assertions also passed for these 11 files; importing `ui.state`/`ui.controller` confirmed neither `oempa.api` nor `oempa.driver` was loaded. GUI import/integration passed against the fake adapter; changed backend source imports passed against the fake API. Static checks confirmed no thread creation or device ownership remains in `gui.py`. Existing hardware-capable diagnostic tests were deliberately excluded. No device connection, configuration load/write, acquisition-enable call, network change, native build, or real GUI launch was performed. Bridge files, configs (including `backup_original.txt`), saved data, focal-law implementation, and FMC/B-scan processors were not edited.

Next action: present Phase 1 results and stop. Phase 2 requires a new user request. Hardware testing remains separately authorized regardless of UI implementation approval.

### UI-development checkpoint — 2026-10-08

The user has authorized transition toward the production OEM-PA Config Program UI. This checkpoint is the active procedure and supersedes the historical next-step/GUI-deferral wording below for UI planning only. The PA findings and all hardware safety constraints remain in force.

Completed: read this file completely; inspected the repository, `main.py`, `gui.py`, every `oempa/` Python module, relevant bridge exports/implementations, SDK driver headers, and representative tests. This task changes documentation only. No device connection, acquisition, configuration load/write, network change, GUI launch, or native build was performed. Stop at architecture review before substantial UI implementation.

#### Reusable implementation

- `main.py` is a minimal GUI launcher; keep that public entry point.
- `gui.py` uses Tk/ttk and embedded Matplotlib. Reuse connection/status widgets, FMC settings, progress, TX/RX selection, waveform plotting, RF/absolute diagonal B-scan viewing, software display gates, logging, and NumPy save behavior incrementally.
- `driver.py` owns handles, connection, acquisition-OFF configuration loading, and the existing reconnect sequence. Preserve working hardware behavior.
- `acquisition.py` prepares storage while OFF, registers the native callback, polls received cycles, stops in `finally`, validates sample encoding, and returns `(cycles, N)`. Its progress callback runs in the acquisition worker, not in the native acquisition callback.
- `config.py` builds MultiHWChannel acquisition/replay FMC configurations. `fmc.py` maps cycles to `(TX, RX, N)` and carries time-axis metadata. Keep the verified full `(16,16,N)` path and mapping.
- `bscan.py` extracts `FMC[e,e,:]`. `focal_law.py` and `pa_config.py` provide offline ideal/quantized steering-law calculation and one-law Standard PA text generation. They do not establish physical steering or acoustic validity.
- `api.py` already provides cycle, A-scan settings, PA receive/delay, configuration-load-stage, callback, and pulser-power snapshots. Keep the C++ bridge and callback storage contract.
- `cscan.py`, `scan_grid.py`, and `scan_session.py` remain internal; no scanner workflow or expansion is planned.

#### Findings and missing interfaces

- The GUI uses one `busy` flag, calls `root.after` from workers, leaves configuration entries editable while busy, and can destroy the window/close the device while a daemon worker still uses it. Connection failure can leave the worker-local device handle unclosed; driver reconnect/cleanup failures also need explicit state handling.
- Acquisition currently checks only cycle count against current GUI entries. There is no draft/applied revision, full readback comparison, or data invalidation after apply/edit. Acquisition becomes available immediately after connection. A failed write must be treated as potentially partial, not as preservation of the previous applied configuration.
- The GUI constructs `FMCProcessor` with `start_us=0` and `sampling_hz=100e6`. Instead aggregate existing snapshots in a backend service and pass actual timing explicitly. Validate timing consistency across relevant FMC acquisition/replay cycles before using one shared cube time axis; do not silently assume cycle 0 describes all channels.
- Add immutable backend result metadata: applied configuration revision, mode, timing, encoding, logical TX/RX mapping, and provenance. Keep existing NumPy array representations and public methods; use an additional metadata record/sidecar rather than replacing `.npy` files. Legacy arrays without timing must request explicit metadata or show sample indices; do not silently assign 100 MHz.
- Add Python wrappers for existing native firmware ID, maximum element/channel count, and aperture-count exports. These report device capability, not physical probe identity. Serial, embedded version, remaining limits, and filter descriptions require documented SDK-backed extensions if needed. Unsupported information displays as unavailable, never as a guessed readback.
- Add a pure user-entered probe profile with element count, pitch, center frequency, material velocity, logical/physical mapping verification, and optional wedge geometry. Unknown values stay unknown; existing calculation assumptions must be labeled as assumptions. Do not infer pulse width automatically from an unverified center frequency.
- Add cooperative cancellation to the acquisition polling interface without changing the native callback. The worker remains responsible for stopping acquisition and cleanup. Blocking SDK calls cannot be assumed cancellable.
- Add structured operation errors/load-stage diagnostics. The current bridge mostly returns success/failure and the Python API raises generic errors; it does not expose a complete AOS warning stream. Investigate documented SDK notification/error hooks before promising warning capture; retain vendor dialogs until safe reporting is verified. Never guess pulser-power estimator inputs or equate current power with candidate required power.
- Existing configuration builders expose limited subsets: FMC has no general start/format editor; PA hardcodes zero start/wedge/center delays, Compression/Signed, and one shared TX/RX aperture. Initially show unsupported fields read-only or unavailable. Extend builders only in separately reviewed, documented steps; do not create arbitrary GUI setters.

#### Proposed layout

- Persistent top strip: OEM-PA endpoint `192.168.1.11:5001`, Connect/Disconnect, explicit connection/operation/acquiring state, and configuration state. Show the fixed endpoint without network-edit controls under the current project constraints.
- Left setup notebook: Device (hardware information/capabilities), Probe (user-entered assumptions and verification), Acquisition Configuration (draft values beside applied/readback values), and mode-specific FMC/PA controls. Apply is an explicit operation; editing a draft performs no hardware writes.
- Large workspace notebook: A-scan, FMC, B-scan, Phased Array, and Imaging/TFM placeholder. Acquisition modes are A-scan/FMC/PA, distinct from display tabs. No automatic configuration load or acquisition when switching tabs/modes.
- A-scan: waveform with microsecond axis from recorded timing, metadata/source, and Matplotlib zoom/pan/reset toolbar. Initially reuse acquired/FMC-selected/saved traces; continuous live acquisition is a later cancellable backend feature.
- FMC: verified 16x16 acquisition action, received-cycle progress out of 256, TX/RX selector, shape/encoding/timing metadata, save/load. Progress is received cycles, not physical pulse count.
- B-scan: label "FMC diagonal pulse-echo B-scan (not mechanically scanned)"; RF/absolute display and software time gates. Gates affect the view, not device settings. MAX-buffer provenance stays visible; RF display does not claim pre-compression RF.
- PA: logical aperture and angle controls, ideal/TX/RX delay table or plot, and explicit physical-validation status. Start with offline preview and saved diagnostic viewing. Preserve the zero-tail warning; no new PA tests or physical steering claims. Linear/sector controls remain future placeholders.
- Bottom action/status strip: Acquire/Stop, progress, draft/applied/stale indication, and expandable timestamped errors/warnings log. TFM is reserved only; no implementation in this task.

#### Proposed module responsibilities

- `gui.py`: retained `OEMPAGUI`/`run_gui` facade and Tk composition; extract view panels gradually into a small `ui/` package only as needed. Tk variables, dialogs, and Matplotlib updates belong exclusively to the main thread.
- `ui/state.py`: pure application state, draft/applied revisions, validation messages, source/probe provenance, and dataset freshness. Device state is disconnected/connecting/connected/disconnecting/error/closing; operations are idle/applying/acquiring/stopping. Configuration is unknown/dirty/invalid/applied.
- `ui/controller.py`: one serialized device worker and command queue, immutable command arguments captured on the Tk thread, cooperative cancellation event, and event queue. A main-thread `root.after` pump consumes events; workers never invoke Tk, including `after`. Tag results with operation/configuration IDs to reject stale events and coalesce progress/live updates.
- `oempa/service.py` (proposed additive facade): orchestrate existing device/configuration/acquisition/snapshot modules; validate mode readiness, prepare/apply/read back configurations, and attach timing/provenance to results. No Tk dependencies or hardware logic moved into views.
- `oempa/probe.py` and a small metadata/persistence module (proposed): pure probe profile and dataset metadata/sidecar loading/saving. Keep imaging transforms in existing backend modules and reserve a later independent TFM module.
- `bridge/` and `api.py`: preserve ABI/callback implementation; add only missing, documented capability/error interfaces when necessary. Pure offline tests should use a fake service without importing the DLL-loading `api.py`.

#### State and safety rules for implementation

Acquisition requires connected/idle state, valid selected mode, a successfully applied/readback-verified matching revision, and no unresolved apply/stop error. Force OFF before configuration writes. Disable hardware configuration controls throughout applying/acquiring/stopping; mode changes affecting hardware mark the draft dirty. Applying becomes successful only after the full load/reconnect/readback sequence. Failure leaves configuration unknown and acquisition blocked until recovery.

Relevant configuration changes mark current acquired data stale and invalidate derived views as current results; preserve original data/metadata for explicitly labeled historical viewing or saving. Software gates, zoom, display mode, and TX/RX selection do not invalidate acquisition. Probe edits invalidate dependent physical interpretation/focal-law/geometry outputs; they affect hardware revision only where the applied law depends on them.

Close requests enter closing state, reject commands, signal cancellation, and keep the Tk event pump alive while the owning worker stops, disconnects, and releases the handle. Never destroy a handle concurrently with a worker or block the Tk thread joining it. Cleanup failures stay visible; never claim acquisition OFF when stopping failed. A blocking SDK call must finish before handle destruction; a future process-isolation design requires separate justification.

#### Incremental implementation plan

1. Architecture review (this checkpoint): documentation only; stop and present the proposal to the user.
2. Safety foundation: additive state/controller/fake-service interfaces; replace worker Tk calls, serialize device operations, implement close/cancellation and partial-failure handling while preserving the present layout. Test state transitions, cancellation/close, stale events, failed apply, and cleanup without hardware.
3. Readback and provenance: service snapshot aggregation, draft/applied verification, actual timing, dataset freshness and sidecar persistence; test nonzero start/non-100-MHz timing, inconsistent-cycle rejection, and legacy metadata behavior offline.
4. Setup UI: incrementally add Device/Probe/Acquisition Configuration panels with source labels and supported editing only. Validate against fake snapshots; no automatic connection, apply, or acquisition.
5. Verified data workflows: integrate FMC, acquired A-scan selection, diagonal B-scan gates, and zoom/reset; preserve `(16,16,N)` and verify mappings against saved/synthetic data. Continuous A-scan follows only after backend support and safe cancellation are ready.
6. PA preview: reuse the focal-law calculator and saved diagnostics; mark unverified mapping/physical steering, keep PA hardware work separately authorized, and leave linear/sector/TFM as placeholders.
7. Later hardware acceptance is a separate explicitly authorized task: first connection/readback and safe apply with acquisition OFF, then specifically authorized acquisition. No hardware acceptance is implied by UI implementation approval.

Validation for this documentation-only checkpoint: inspect the document diff and confirm only `AGENTS.md` was edited. Do not run the full test suite: many existing scripts connect, write configurations, or acquire ultrasound. No hardware diagnostic or native build is appropriate for this change.

### Preserved backend diagnostic checkpoint

1. **Last completed step**
    Completed the authorized Stage 2 single-RX element-7 PA acquisition using the Stage-1-verified candidate. The configuration was reloaded with acquisition OFF, readbacks passed, one cycle-0 callback was observed, acquisition was turned OFF immediately, and the device was disconnected OFF. A new waveform was saved and compared offline with the 16-RX Compression reference.

2. **Verified result**
    Hardware readback before enabling acquisition remained verified: CycleCount 1; MultiChannel disabled; TX/RX apertures 0..15; TimeSlot 2600 us; zero TX/RX delays; analog gain 20 dB; digital gain 0 dB; Start 0 us; Range 30 us; PointCount 3001; sampling 100 MHz; filter 1.

    One cycle 0 callback was observed. Header metadata: dataCount 3001; dataSize 1 byte/sample; signed true; bitSize enum 0; expected bytes 3001. Raw `pBufferMax` statistics calculated in the callback: first nonzero index 0; last nonzero index 192; 188 nonzero samples; 2808 terminal zero samples; every sample after the last nonzero was zero. Window indices 185..205 were eight `0x01` samples (185..192) followed by thirteen `0x00` samples (193..205).

    Both bridge copies were 3001 bytes and byte-identical; callback metadata matched bridge metadata. The callback raw window matched the single-A-scan bridge window. The single-copy and multi-copy first/last/nonzero/suffix statistics matched callback-time statistics. The NumPy array was shape `(3001,)`, dtype `int8`; its bytes matched the multi-A-scan copy. The saved `data\pa_0deg_callback_integrity.npy` reloaded exactly equal to that NumPy array and had matching statistics. Therefore the tail already exists in raw `pBufferMax`; bridge copying, Python conversion, and `.npy` serialization did not introduce it.

    Acquisition was requested OFF immediately after observing the callback, confirmed by successful `eAcqOff`, forced OFF again before disconnect, and the device disconnected. Polling is asynchronous; physical pulse count is unknown and is not claimed to be exactly one.

    **1. Directly documented facts**
    - `UTKernelStream.h` defines `CSubStreamAscan_0x0103`: `dataCount` is a 16-bit point count; `dataSize` is bytes per point; `sign` and `bitSize` describe encoding; `max`, `min`, and `sat` mark the corresponding buffers valid. The header has no second/partial valid-sample count. `structAcqInfoEx` carries encoders, digital inputs, temperature, device ID, MultiChannel/FMC flags, and FMC element index, but no A-scan valid length.
    - `UTBasicType.h` documents `dataCount * dataSize` as the total size of each max/min/saturation buffer. `pBufferSat` has only its LSB significant. The callback contract describes `pBufferMax`/`pBufferMin` as arrays of points.
    - `4_Software_API.pdf` and `7_Software_Functions_&_Parameter_List.pdf` define `dataCount` as PointCount and `dataSize` as the size in bytes of one value (for 8-bit data, 1 byte). `SetAscanRange` derives PointCount/PointFactor from the requested range and digitizing clock when those are not explicitly supplied. The manuals provide no separate sample-valid-length field.
    - For `eCompression`, the A-scan is peak-held: `pBufferMax` carries maximum values and `pBufferMin` minimum values. `eDecimation` instead reduces sampling frequency and may lose extrema. The saturation buffer is a separate indication; the manual says positive saturation data means the beam signal after reception focusing is too high. These buffers describe the full callback point count, not a shorter receive interval.
    - The verified PA config has Range 30 us, PointCount 0 (automatic), Compression, Signed, GateCount 0, `Focusing=Standard`, 16 receiver delays for one focal law, `FocalTimeOfFlight=0`, and zero receiver center/wedge delay. Hardware readback reported PointCount 3001 and 100 MHz.
    - The parameter-list manual says Standard reception focusing has focal count 1; DDF has more than one focal law and uses focal-TOF values to trigger switching between delay patterns. For Standard focusing, the single focal-TOF value is explicitly “not significant.” `EnableDDF` selects dynamic pattern switching versus using a static delay pattern. The manual defines wedge delay as the delay of the mechanical/electronic wedge. It does not define `CenterDelay` as a receive-window length.

    **2. Vendor-source behavior**
    - `OEMPAApplicationExampleDlg.cpp` registers `CallbackAcquisitionAscan`. Its callback records frame ID and encoder and increments a byte counter by `dataCount * dataSize`; it does not read, display, crop, or inspect `pBufferMax`, and does not use any other valid-length member.
    - OEMPATool's `CChildView::ProcessAcquisitionAscan_0x00010103` checks the header/pointer, allocates by `dataCount`, records size/sign/bitSize, and copies exactly `dataCount * dataSize` bytes from `pBufferMax` (and from `pBufferMin` when that build option is enabled). It does not crop the A-scan by focal TOF, gate, or a second length field.
    - The SDK C# wrapper forwards the callback headers and buffer pointers to the registered user callback. The Matlab wrapper stores/copies `dataCount * dataSize` bytes; its callback guard compares the received point count with its preallocated maximum, but does not derive a shorter valid span within a record.
    - The exposed `OEMPA_WriteHW` path applies `SetAscanRange`/`SetAscanRangeWithCount`/`SetAscanRangeWithFactor`, then, for non-FMC PA cycles, calls `SetReceptionFocusing` with the focal-TOF array and center delays and calls `EnableDDF` with the focusing mode. No later A-scan buffer crop/valid-count operation appears in that exposed write path.
    - The known-good FMC config is materially different: CycleCount 256 and `EnableMultiChannel=1`, one hardware-acquisition cycle plus replay cycles, per-cycle receiver selection, and Start/Decimation arrays. It does not use the normal PA `Focusing`/`FocalTimeOfFlight` receiver configuration. Its A-scans therefore do not prove that the distinct normal-PA beamformed receive path must produce the same waveform support.

    **3. Hypotheses not verified**
    - The callback-time zeros may be the actual zero-valued output of the normal-PA receive/beamforming path or the hardware signal path. The public documents/source do not explain why that path produces zeros after index 192.
    - Because `pBufferMax` is a compressed maximum envelope rather than pre-compression RF, the tail could reflect the peak-hold output while `pBufferMin` differs; the integrity test did not record the header `min`/`sat` flags or capture those buffers.
    - The documented semantics make `FocalTimeOfFlight=0` an unlikely explanation for a shortened window in the verified one-law Standard mode. `CenterDelay` behavior beyond its use as a focusing API argument is not specified in the searched manuals; no evidence connects it to a shorter `dataCount` or receive window.

    The latest authorized callback diagnostic observed: `dataCount=3001`; `dataSize=1`; signed true; `bitSize=0`; expected byte count 3001. Validity flags MAX/MIN/SAT were `True/False/False`; pointer state was non-null/null/null, so only MAX was analyzed and MIN/SAT were not dereferenced. MAX first/last nonzero indices were `0/193`; nonzero samples 189; exact zeros 2812; terminal zeros 2807; min/max `-106/127`. Index 193 itself was nonzero, so samples 193..3000 were not all zero; all samples 200..3000 were zero. The 185..205 window had nine `0x01` samples (185..193), then twelve `0x00` samples (194..205). Windows 200..300, 500..600, 1000..1100, 2000..2100, and 2900..3000 each contained 101 exact-zero MAX samples.

    The validity flags and pointer presence agreed for MAX, MIN, and SAT. MAX bridge copies, NumPy array, and `data\pa_0deg_callback_buffers.npy` agreed with callback-time MAX statistics; single and multi bridge copies were byte-identical. No MIN or SAT content was available from this unchanged configuration. The callback run had acquisition OFF before loading, immediately after callback observation, and before disconnect. Polling is asynchronous; physical pulse count is unknown and is not claimed to be exactly one.

    Stage 1 Decimation candidate: `configs\pa_test_0deg_timeslot_2600us_decimation_stage1.txt`. Offline `parse_configuration` returned `{'cycle_count': 1, 'multi_channel_enabled': False}`. Exact text differences from the verified Compression config were line 11 `PointCount=0` -> `PointCount=3001` (same effective count, now explicit) and line 12 `CompressionType=Compression` -> `CompressionType=Decimation`; no other config lines changed. This ensured the existing `OEMPA_WriteHW` path used `SetAscanRangeWithCount` instead of its automatic Compression branch.

    The load stages all completed: `eReadFileWriteHW_Enter=True`, `eWriteHW_Enter=True`, `eWriteHW_Leave=True`, `eReadFileWriteHW_Leave=True`; parsed cycle count 1. No UTKernel/pulser-power warning appeared. Hardware readback passed: CompressionType enum 1 (`eDecimation`); Range 30 us; PointCount 3001; PointFactor 1; sampling 100 MHz; TimeSlot 2600 us; CycleCount 1; MultiChannel disabled; TX/RX apertures 0..15; all TX/RX delays zero; analog gain 20 dB; digital gain 0 dB; Rectification enum 0 (`eSigned`); bit-size enum 0 (`e8Bits`); filter 1; RX focusing enum 0 (`eStandard`); DDF disabled; one RX focal law; focal TOF and emission/reception wedge delays zero.

    Pulser-power observation: max 15.00 W; current 0.33 W. Current power is not treated as required configuration power. Acquisition was forced OFF before load, after load, and before disconnect. No acquisition-enable function was called.

    Stage 2 Decimation callback metadata: cycle 0; `dataCount=3001`; `dataSize=1`; signed true; `bitSize=0`; expected bytes 3001. MAX/MIN/SAT flags were `True/False/False`, pointers non-null/null/null. Hardware readback matched Stage 1: Decimation enum 1; Range 30 us; PointCount 3001; PointFactor 1; sampling 100 MHz; TimeSlot 2600 us; CycleCount 1; MultiChannel disabled; TX/RX 0..15; zero TX/RX delays; gains 20/0 dB; Signed 8-bit; filter 1; Standard focus; DDF off; one zero-TOF focal law.

    Decimation MAX callback statistics: first/last nonzero `1/193`; 188 nonzero samples; 2813 exact zeros; 2807 terminal zeros; min/max `-106/127`. Samples 193..3000 were not all zero because index 193 was nonzero; the exact zero suffix starts at 194. Window 180..210 contained fourteen `0x01` values (indices 180..193) and seventeen `0x00` values (194..210). Windows 200..300, 500..600, 1000..1100, 2000..2100, and 2900..3000 each had 101 exact-zero MAX samples. NumPy shape `(3001,)`, dtype `int8`; 100 MHz, 0.010000-us interval, 30.000-us record. RMS (sample counts) for 0–1, 1–2, 2–5, 5–10, 10–20, 20–30 us: `40.1096, 41.9135, 0, 0, 0, 0`.

    Saved Decimation waveform: `data\pa_0deg_2600us_decimation_ascan.npy`; callback-to-bridge-to-NumPy-to-file checks passed. Offline comparison with `data\pa_0deg_2600us_ascan.npy` (Compression) found: Compression first/last nonzero `0/192`, Decimation `1/193`; each has 188 nonzero samples and 2813 exact zeros. Compression zero suffix starts at 193, Decimation at 194. Nonzero-mask intersection 186, union 190, differing positions 4, Jaccard `0.978947`. Common-support RMS was `42.5848` Compression and `42.5371` Decimation; Pearson correlation `0.977276`. Both have zero nonzero samples in all windows from 2 us onward. The zero-tail behavior therefore persisted under Decimation; no late-window activity appeared.

    Acquisition was enabled briefly until callback observation; the number of physical ultrasonic pulses is unknown. It was turned OFF immediately, confirmed OFF before disconnect, and the device disconnected. No parameters were changed and no pulser-power warning appeared.

    Single-RX Stage 1 candidate: `configs\pa_test_0deg_timeslot_2600us_single_rx7_stage1.txt`. Element 7 was selected as one of the two central logical elements (7/8) in the 16-channel aperture; no physical probe mapping is inferred. Offline `parse_configuration` returned `{'cycle_count': 1, 'multi_channel_enabled': False}`. Exact diff versus the verified 16-RX Compression reference was limited to receiver-array fields: `Element.count=16` -> `1`; receiver Element list `0..15` -> `7`; `Delay.count=16;1` -> `1;1`; 16 zero delays -> one zero delay; `Gain.count=16` -> `1`; 16 zero gains -> one zero gain. TX fields and all acquisition settings were unchanged.

    The load stages all completed: `eReadFileWriteHW_Enter=True`, `eWriteHW_Enter=True`, `eWriteHW_Leave=True`, `eReadFileWriteHW_Leave=True`; parsed cycle count 1. No UTKernel/pulser-power warning appeared. Hardware readback passed: CycleCount 1; MultiChannel disabled; TX aperture 0..15; RX aperture `[7]`; Compression enum 0; Range 30 us; PointCount 3001; PointFactor 256; sampling 100 MHz; TimeSlot 2600 us; TX delays all zero; RX delay count 1 and delay zero; analog/digital gain 20/0 dB; Rectification enum 0 (`eSigned`); bit-size enum 0 (`e8Bits`); filter 1; RX focusing enum 0 (`eStandard`); DDF disabled; one zero-TOF focal law; one RX gain at 0 dB; wedge delays zero. `PulserPowerMax` was 15.00 W and `PulserPowerCurrent` was 0.33 W; current power is not interpreted as required configuration power. Acquisition was forced OFF before load, after load, and before disconnect. No acquisition-enable call was made.

    Stage 2 re-read the required configuration values and all passed: CycleCount 1; MultiChannel disabled; TX aperture 0..15; RX aperture `[7]`; Compression enum 0; Range 30 us; PointCount 3001; PointFactor 256; sampling 100 MHz; TimeSlot 2600 us; all TX/RX delays zero; analog/digital gains 20/0 dB; Signed 8-bit; filter 1; Standard focusing; DDF disabled.

    One cycle-0 callback was observed. Callback metadata: `dataCount=3001`, `dataSize=1`, signed true, bitSize enum 0. MAX/MIN/SAT flags were `True/False/False` with pointers non-null/null/null. MAX raw statistics: shape `(3001,)`, dtype `int8`, first/last nonzero `0/2151`, 197 nonzero samples, 2804 exact zeros, terminal zero count 849, min/max `-106/127`. The suffix from index 2152 through 3000 is exactly zero; samples 193..end are not all zero. Window 180..210 contained nine `0x01` samples (180..188) then zeros. MAX RMS for 0–1, 1–2, 2–5, 5–10, 10–20, 20–30 us: `40.6259, 42.1240, 0.1528, 0, 0.0548, 0.0632`. Sampling frequency 100 MHz; interval 0.010000 us; record duration 30.000 us.

    Saved to `data\pa_0deg_2600us_rx7_ascan.npy`. Callback-time MAX, both bridge copies, NumPy representation, and saved file were consistent; the bridge copies were byte-identical.

    Offline comparison to the verified 16-RX Compression trace (`data\pa_0deg_2600us_ascan.npy`): Compression first/last nonzero `0/192`, RX7 `0/2151`; Compression nonzero/zeros `188/2813`, RX7 `197/2804`; Compression zero suffix starts at 193, RX7 at 2152. Nonzero-mask intersection 182, union 203, differing positions 21; Jaccard `0.896552`. Pearson amplitude correlation over shared nonzero positions was `0.998800` (common-support RMS 43.0505 Compression, 43.3797 RX7). Compression had no nonzero samples from 2 us onward. RX7 had 7/300 nonzero samples in 2–5 us, none in 5–10 us, 3/1000 in 10–20 us, and 4/1001 in 20–30 us. These late values are sparse and are not identified as echoes.

    Acquisition was enabled briefly until callback observation. Polling/callback timing is asynchronous; the physical ultrasonic pulse count is unknown. Acquisition was requested OFF immediately after callback observation and again before disconnect. No parameters were changed; no pulser-power warning appeared.

3. **Current unresolved problem**
    The 16-RX trace ends at index 192, while the single-RX element-7 trace contains sparse nonzero values through index 2151. This supports an association between the prior zero-tail behavior and the multi-element receive/beamforming path, but does not establish the AOS mechanism. RX7 also has no nonzero samples in 5–10 us and only a few in later windows; these are not confirmed acoustic echoes. Actual signal/hardware/probe behavior remains possible.

    **Classification:** the result favors layer 3 (normal-PA multi-element receive/beamforming) over a Compression-only explanation, with limited confidence. Layer 4 (actual signal/hardware/probe behavior) remains possible. Saved-data/NumPy and bridge-copy handling remain exonerated. `pBufferMax` is the vendor callback MAX output, not pre-compression RF.

4. **Immediate next step**
    No further hardware test is established yet. Review the RX7 trace and AOS normal-PA receive/beamforming semantics; request vendor guidance if needed. Do not automatically test RX8, RX0, or another aperture.

5. **Steps after that**
    If another controlled experiment is proposed, identify one specific question not resolved by the RX7 comparison and obtain separate explicit authorization first. Continue to defer physical interpretation until probe mapping, probe identity, coupling geometry, and material velocity are verified.

6. **Do not do yet**
    Do not perform another acquisition or test another RX aperture without separate authorization. Do not change TimeSlot, pulse width, TX aperture, gain, range, filtering, sampling, focal laws, DDF, gates, callback implementation, or network settings. Do not enable MIN/SAT outputs or interpret early peaks/sparse late values as confirmed echoes. Keep acquisition OFF.

## Useful existing diagnostics/APIs
The current bridge/API may already contain functions for:
- configuration load diagnostic callbacks
- cycle snapshots
- A-scan configuration snapshots
- PA receive snapshots
- PA delay snapshots
- multi-A-scan callback storage
- MultiChannel state
- configuration parser

Reuse these rather than duplicating them.

## AOS source behavior relevant to the load failure
`OEMPA_ReadFileWriteHW(...)` ultimately calls `OEMPA_WriteHW(...)`.

The vendor write path can fail before its `eWriteHW_Leave` callback. The normal focal-law write sequence includes TX and RX wedge delay, widths/gains, delays, aperture enables, RX focusing, and DDF. `UnlockDevice(eAcqState)` can also make the overall operation fail.

Individual setter success does not prove that the full configuration is valid because the full write path performs additional system-level validation, including pulser-power constraints.

## Do not overclaim
When reporting results, distinguish clearly among:
- offline parser success
- individual setter success
- hardware readback success
- full configuration-write success
- acquisition success
- physical acoustic/steering validation

These are not interchangeable.

A successful software/hardware delay readback does not prove the beam is physically steering in the intended direction through the actual probe/wedge/material.

## Longer-term roadmap after current issue
Only after the pulser-power/load issue is resolved:
1. Establish a safe, valid conventional PA configuration.
2. Re-run controlled PA acquisition.
3. Investigate the exact-zero A-scan tail if it persists.
4. Verify probe channel mapping and actual probe specifications.
5. Verify wedge/direct-contact geometry and material velocity.
6. Validate physical steering direction.
7. Implement sector/linear PA scan behavior.
8. Add TFM using the already-working FMC dataset.
9. Integrate verified PA/TFM controls into the GUI.
10. Improve GUI thread safety/state handling later; backend correctness comes first.

Do not jump ahead to TFM/GUI work while the conventional PA hardware configuration is unresolved.

### FMC emission getter diagnostic — SDK inspection checkpoint (2026-10-08)

The current authorized task is read-only diagnosis only; Stage 3C remains blocked. No acquisition, configuration load/write, callback registration/storage resize, or new provenance exception is authorized in this diagnostic.

Installed x64 UTKernelDriverOEMPA.h declares GetEmissionEnable(int cycle, DWORD aperture[g_iOEMPAApertureDWordCount]), GetEmissionWidths(int cycle, int &elementCountMax, int *elementCount, float *width), and GetEmissionDelays(int cycle, int &elementCountMax, int *elementCount, float *delay). Each bool returns call success separately from output data. The aperture is a four-DWORD bitmap; float getters do not accept an aperture. SDK maximum allocation is 64 floats; the actual 16:16 bridge uses capacity 16. Vendor CustomizedDriverAPI.cpp ReadHWWriteFileMultiHWChannel initializes output counts to zero and reads widths/delays before aperture; OEMPA_ReadHW invokes this path for every cycle, including replay. The C# wrapper also uses the supported callback-array overload with maximum 64. Thus no aperture prerequisite or base-cycle-only restriction is present in the exposed vendor readback path. Raw getter implementation bodies are not exposed; unchanged successful outputs must not be inferred as hardware state.

The existing extended bridge uses correct types/order and capacity 16, but initializes width/delay output counts to -1. Historical normal-PA Stage-2 validation read 16 widths near 0.5 us and 16 zero delays successfully through that same bridge. No production bug is established yet. Added a diagnostic-only native export and Python wrapper recording count/capacity/data immediately after getter and after UnlockDevice(eAcqOff), with valid count seeds 0/1/16 and capacities 16/64. Aperture seeds contain only valid logical 0..15 bits. A guarded opt-in script will read existing FMC hardware state without reapplying any file. Build command cmd /c bridge\build_bridge.cmd succeeded; only existing C4005/C4091 warnings. Fake-DLL wrapper tests: 9 passed before real-device diagnostic. Production acquisition/readback policy remains unchanged.

### Completed FMC TX aperture/width/delay diagnostic (2026-10-08)

Current decision: C for the observed AOS 1.1.5.4 SDK/driver/device state. Normal PA historical readback supplies widths/delays; current MultiHWChannel base-cycle width/delay getters return success without replacing their outputs. This characterizes an SDK/driver MultiHWChannel readback limitation, not a proved general TX getter failure. No bridge bug or alternate calling convention was established. Stage 3C remains blocked; no TX width/delay provenance exception was added, and no acquisition is authorized by this checkpoint.

Executed only tools/diagnose_fmc_emission_readback.py against the existing loaded FMC state, UTC 19:35:21.909305..19:35:28.538850. CycleCount 256; MultiChannel supported/enabled true. No configuration load/write occurred. All 70 getter calls and unlocks succeeded. Aperture reads from two valid seeds converged to logical [0], [1], [2], [15] on base cycles 0,16,32,240 and [] on replay cycles 1,17,241. Both width and delay getters on every selected base cycle left all 64 float sentinels and count seeds unchanged, immediately and after unlock: capacities/count seeds 16/0,16/1,16/16,64/0. Maximum-capacity arguments stayed unchanged. Therefore neither zero initialization, valid nonzero count initialization nor SDK-maximum allocation recovered TX values. Unchanged outputs are not hardware state. Replay counts 1/16 changed to 0 after unlock while float buffers remained untouched, demonstrating deferred output handling and a real zero-length replay result.

Historical safe normal PA evidence in artifacts/phase5_stage2/validation.json shows aperture 0..15, 16 widths near 0.5 us and 16 zero delays through the same production getter bridge. No additional PA configuration write was required/performed. Inspected supported OEMPA_ReadHW focal-law structures use the same raw getters; compatibility APIs forward to them. C# callback-array overloads are exposed but not independently tested, and no source evidence establishes a distinct hardware TX representation there. No trustworthy independent alternative MultiHWChannel TX width/delay hardware readback was found. Parsed/software/cache state would not establish hardware truth.

Added only a read-only diagnostic bridge export, additive ctypes observation wrapper, guarded script and two fake-DLL tests; rebuilt bridge DLL/compiler outputs. No GUI/acquisition/verifier/provenance behavior changed. Detailed contracts, evidence, count matrix and commands: artifacts/phase5_fmc_emission_readback/findings.md. Exact complete seeded arrays/API success/count/capacity/after-unlock observations: artifacts/phase5_fmc_emission_readback/diagnostic.json.

Safety confirmed: acquisition OFF on connect, every diagnostic lock/unlock and before disconnect; no acquisition enable, callback registration, callback-storage resize, EnableFMC, SetUnlockEnableShot, OEMPA_WriteFileText, config rewrite or network modification. Clean disconnect/handle release true; protected configs/data SHA-256 checks unchanged true. No SDK error was reported by getter/unlock returns.

Validation: cmd /c bridge\build_bridge.cmd succeeded (existing C4005/C4091 warnings). Explicit offline commands: python -m unittest discover -s tests -p 'test_ui_*.py' -q -> 128 passed; python -m unittest discover -s tests -p 'test_tfm_offline.py' -q -> 20 passed. AST syntax checks for oempa/api.py, tools/diagnose_fmc_emission_readback.py and tests/test_ui_native_wrapper_offline.py passed. Baseline 146 preserved plus 2 new tests = 148 passing offline tests. Stop here; do not proceed to Stage 3C or acquisition.
