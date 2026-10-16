Ã¯Â»Â¿# FMC latency: instrumentation and evidence

## Current status: FMC acquisition-speed issue solved - 2026-10-15

The operator supplied the following real-hardware benchmark after deploying batched OFF readback. These are operator-reported OEM-PA measurements, not synthetic/offline test timings and not a new hardware run by this agent. Historical investigation/candidate notes below are preserved chronologically; this completion record supersedes their pending-benchmark status.

| Metric | Before batching | After batching |
|---|---:|---:|
| full_snapshot | 35.1942 s | 0.7579 s |
| preparation | 35.3665 s | 0.9154 s |
| first_frame | 0.5078 s | 0.5079 s |
| total | 36.1138 s | 1.6321 s |
| Snapshot LockDevice calls | 528 | 1 |
| Snapshot UnlockDevice calls | 528 | 1 |
| Snapshot Flush calls | 0 | 2 |

Total Acquire time decreased by approximately95.48% (22.13x faster), while the actual first-frame interval stayed essentially unchanged at0.508s. The solved bottleneck was synchronization around full readback, not physical acquisition timing. Full verification was retained, not cached or reduced.

Reported optimized SDK details: FMCBatch.LockDevice1 call (duration not supplied); FMCBatch.UnlockDevice1 call/0.1290s; FMCBatch.Flush2 calls/0.4000s combined. Other measured stages: initial_off0.0047s, topology_refresh0.1251s, python_verification0.0176s, storage_off0.0095s, sdk_on0.0332s, first_callback_latency0.0331s, shutdown_off0.0281s, record_copy_validation0.0027s, cube_construction0.0001s, metadata_verification0.0013s, gui_render0.0878s. Intervals can overlap; do not sum them as disjoint stages.

Operator-reported integrity: accepted first frame256/256,13 post-frame shutdown callbacks, unexpected0,malformed0; cube(16,16,3001), signed int8 amplitude range-128..127;562/768256 representation-limit samples(0.0732%). No gain/timing/parameter change is implied by amplitude limits. Shutdown callbacks do not overwrite the immutable first frame. Physical firing count remains Unknown; physical probe/channel mapping remains unverified. Dataset persistence/reload results were not supplied for this benchmark and are not claimed here.

### Production/default and clean GUI log

Production automatically uses the batch export for valid applied full16x16 FMC, on both Apply and Acquire, with all fresh readbacks and verification unchanged. Static PE export inspection (no DLL execution/device access) confirmed that runtime bridge/oempa_bridge.dll exports OEMPA_GetFMCSnapshotBatch, as does the candidate. Python loads the default filename; build_bridge.cmd defaults to that same filename. No experimental flag or alternate DLL selection is needed. Existing old-DLL compatibility remains only for a missing export; supported-batch failure cannot retry via old/cached reads. No rebuild/replacement or hardware connection was necessary for this closeout.

Routine timing summaries and verbose successful-acquisition dumps are now removed from the GUI log. FMC completion uses one line with shape, first-frame count and any shutdown-callback count. Real errors, post-frame anomalies/chronology warnings and representation-limit notices remain visible. Detailed timing, warnings, per-method counts and frame chronology remain in the dataset metadata/sidecar and backend diagnostics; instrumentation and acceptance logic remain enabled. A-scan/PA behavior is unchanged.

Closeout validation:247 safe UI/native-synthetic tests plus27 offline TFM tests passed (274 total); syntax/audit and protected-file hashes passed. A supplemental desktop screenshot validator stalled on its first capture; its own fake-backend window was closed normally, then its interrupted screenshot reported application-destroyed. It is not counted as a visual pass. No production GUI/device was touched.

The before/after values above close the FMC acquisition-speed issue for this verified workflow. No further speed optimization or hardware benchmark is requested by this closeout.


## Historical instrumentation and investigation notes

No hardware benchmark was performed in the original instrumentation change. The reported 9-10 seconds is an operator observation, not a measured baseline. No speed optimization, configuration change, reduced readback or acceptance shortcut was made. Measurement must precede optimization.

## Observations available on the next separately authorized attempt

`oempa/timing.py` retains first-wins Python perf_counter observations. The bridge retains seven first-wins QPC ticks per attempt, read outside the callback. Windows Python/QPC clock compatibility is checked before alignment; unavailable measurements are omitted and warned about. Native ticks are also retained verbatim. These are observational additions only.

| Milestone | Recorded name |
|---|---|
| T0 request / worker start | requested / worker_start |
| Fresh OFF snapshot / verification complete | preflight_readback_done / preflight_verified |
| T1/T2 SDK ON entry / return | sdk_on_enter / sdk_on_return |
| T3 first valid cycle-zero callback | first_callback |
| T4 final required samples copied | frame_complete |
| T5 worker OFF request | off_request |
| SDK OFF entry / T6 return | sdk_off_enter / sdk_off_return |
| Validated record copy | records_copied |
| T7 cube constructed / T8 metadata verified | cube_built / metadata_verified |
| T9 GUI receives result / UI update | gui_delivered / gui_update_done |
| T10 first subsequent Matplotlib draw completes | draw_complete |

The profile reports preparation/readback/verification, ON lock overhead and SDK time, first callback latency, first-frame interval, worker wake/stop latency, shutdown/OFF, copy/validation, cube, metadata, GUI queue/update/render and total. Durations can overlap: callbacks may arrive before ON returns. Do not sum overlapping intervals. Total includes worker queue time; no missing observation is replaced with zero. One aggregate `[TIMING]` line is logged after drawing. Accepted dataset JSON sidecars retain `timing_profile`; failed attempts retain the backend's last profile and existing bounded rejection diagnostics, without accepting data.

Existing immutable-frame evidence preserves accepted/pre-completion errors, post-frame callbacks, malformed/unexpected counters, complete boundary and bounded chronology. No per-callback logging/file I/O/device access or storage resize was added. The final copy still precedes completion notification; OFF still precedes publication. Normal A-scan and PA paths are unchanged.

## Vendor evidence and TimeSlot

Inspected installed AOS 1.1.5.4 `UTKernelDriverOEMPA.h` MultiHWChannel declarations and `UTCustomizedDriverAPI/CustomizedDriverAPI.cpp`. The latter calls SetTimeSlot for each logical cycle and represents their durations as HWAcquisitionTime/HWReplayTime. Dedicated-FMC subslot code is a distinct branch and is not this workflow.

AOS `4_Software_API.pdf`, sections 6.1, 6.3.2, 6.3.4, 6.4, 6.5.4 and 6.6.2 (parallel acquisition/replay discussion, pages 106-126), describes simultaneous receiver capture into hardware memory during HW acquisition, then processing/returning saved receiver data during replay. Replay does not transmit ultrasound. `7_Software_Functions_&_Parameter_List.pdf`, cycle-list section (pages 8-9), describes per-cycle TimeSlot duration. Vendor materials remain external; extracted copies are local ignored evidence, not redistributed source.

Thus the configured table has 16 pulse-bearing HW acquisition entries and 240 receiver replay entries, producing 256 logical records. This does not establish the physical firing count of a continuous ON/OFF attempt. Physical firing count remains Unknown. At 2000 us for all 256 logical slots the nominal table-duration sum is 0.512 s, not 0.032 s; neither arithmetic result measures SDK, transport, OFF/draining, preflight or GUI overhead. TimeSlot remains unchanged.

Fresh full OFF readback/verification is deliberately retained on every Acquire. It is a possible latency source, not an established bottleneck. No remaining delay can be attributed responsibly until actual stage timings are collected.

## Before / after

| Stage | Before | After instrumentation |
|---|---|---|
| Preparation / readback | Not measured | Pending hardware observation |
| SDK ON / first callback | Not measured | Pending hardware observation |
| First 256-record frame | Not measured | Pending hardware observation |
| Shutdown / OFF | Not measured | Pending hardware observation |
| Cube / verification | Not measured | Pending hardware observation |
| GUI / display | Not measured | Pending hardware observation |
| Total | Operator reports approximately 9-10 s | Not measured; no speedup claimed |

## Exact next manual step

1. Safely Stop, Disconnect and close existing GUI processes before rebuilding. The current default DLL was locked during this task; the running process was left alone. `cmd /c bridge\build_bridge.cmd oempa_bridge_timing.dll` successfully built a candidate, but runtime uses `oempa_bridge.dll`. With the GUI closed, run `cmd /c bridge\build_bridge.cmd` to deploy the new default DLL. Do not hot-replace a loaded DLL.
2. Launch `python main.py`. Under separate explicit operator authorization for one hardware acquisition, use the established production FMC workflow: unchanged SHA256-matched `configs/fmc16_full.txt`, acquisition OFF, apply/readback Verified (mixed sources), 256 x actual point-count preallocation. Stop on any discrepancy; do not weaken verification.
3. Start once, let the existing immutable-frame worker finish and turn OFF. Do not automatically retry. Inspect the aggregate `[TIMING]` line and counters. Save a new dataset/JSON sidecar only if normal acceptance succeeds. Preserve mixed-source provenance and unverified physical mapping.
4. Safely disconnect/close. Compare `timing_profile` stages in the sidecar before proposing any optimization. Failed attempts are not benchmarks of successful acquisition; retain their diagnostics without publishing a cube. No B-scan/TFM or extra acquisition is necessary for this measurement.


## Detailed preparation diagnostic - 2026-10-15

An operator reports `preparation=35.0121s`. That single aggregate cannot identify its cause. It spans worker_start through on_call_enter and currently includes:

1. Explicit acquisition OFF (native LockDevice/UnlockDevice(eAcqOff)).
2. Fresh topology refresh: CycleCount and MultiHWChannel support/enabled, each existing native lock/read/unlock path.
3. Full 256-cycle snapshot: 256 normal snapshots +256 MultiHWChannel snapshots +16 independent base-cycle emission snapshots =528 native snapshot calls. Each has its existing separate lock/getter/unlock sequence. Normal snapshots read gains, timing/format/count/filter/apertures; extended snapshots read classification/start/decimation and separate TX fields. Broken documented getters remain unavailable with approved provenance; they are not reinterpreted.
4. Python snapshot assembly/start derivation and full mode-aware verification.
5. Acquisition prepare: another safety OFF, count/storage reset, callback registration when needed, clear and sample preallocation, then chronology/frame arming.

New `preparation_stages_s` stores initial_off, topology_refresh, full_snapshot, python_verification, storage_off, storage_set_count, storage_register_callback (only when performed), storage_clear, storage_allocate and arm_chronology_and_frame. The sum need not equal preparation exactly: Python dispatch and local diagnostic collection have overhead. Registration absent on later attempts means not performed, not a fabricated zero.

`preparation_sdk` stores bounded native count/total_s/max_s by export and SDK method, separately for off_readback and storage. LockDevice/UnlockDevice are separate from each getter, so deferred SDK work during unlock can be distinguished from getter execution. Do not attribute an unlock delay to a specific preceding getter without additional evidence. Calls preserve original arguments, short circuit, order and result/error handling; profiling has no retries. The collector has64 fixed method entries, aggregates instead of retaining per-cycle rows, reports overflow, is opt-in/thread-local to the owning worker and disabled before acquisition ON. No callback instrumentation or storage/acceptance changes were made here. One aggregate line includes preparation stages and the five highest SDK totals; all entries persist in timing_profile. Missing exports warn and full verification still runs. Native candidate `oempa_bridge_preparation.dll` builds separately; close/disconnect normally and rebuild the default DLL before collecting these observations.

### Can verification be reused safely?

Not established by the current interfaces. Matching GUI draft/applied revisions, same handle and unchanged source hash prove local intent; matching CycleCount/MultiChannel alone cannot detect external changes to gain, timing, filter or apertures. The production full-readback check detects these today and remains enabled. Reconnect, failed/uncertain writes, dirty/stale revisions, cancelled operations and device errors must never inherit verification from an earlier session.

AOS UTKernelDriverOEMPA.h exposes GetSettingId(DWORD*), swGetSettingId() and SetSettingId(DWORD). Software_API callback documentation says the application setting software is responsible for assigning the setting identifier. CustomizedDriverAPI.cpp's optional callback explicitly calls SetSettingId during read/write workflows. Thus this is not documented as a device-maintained monotonic revision/checksum covering every configuration mutation. swGetSettingId is explicitly cached software state. Neither is sufficient to assert unchanged hardware. No new ID write or guessed getter was added. SDK acquisition-status flags/our local boolean likewise do not replace a successful explicit OFF operation.

A future reuse policy would require demonstrated trustworthy mutation detection or an explicitly accepted exclusive-control assumption, plus current connected-session identity, matching requested/applied revision/mode/hash, full verified baseline, no uncertainty and successful OFF/current safety checks. Preserve field-level provenance and distinguish earlier verification from fresh observation in metadata. No such assumption has been silently introduced, and no reuse path is implemented.

### Next measurement and optimization decision

With the new default bridge deployed, collect one normal production FMC timing profile only under separate explicit hardware authorization; keep unchanged configuration and normal verification. Save a new accepted sidecar and share its preparation_stages_s/preparation_sdk sections, plus aggregate log. There is no authorization to fire in this diagnostic task, and no hardware calls were made. The new instrumented run must identify whether costs are in OFF, topology, LockDevice, individual getters, UnlockDevice, Python assembly/verifier or storage before any redundant call can be selected. A 35.0121s total alone is insufficient; after figures and speedup remain unmeasured. Full verification on Apply and Acquire remains unchanged.


## Measured lock bottleneck and full-coverage batching - 2026-10-15

The operator supplied a second hardware timing profile. These are operator observations, not a hardware run performed during this implementation:

| Metric | Before (operator measurement) | After candidate |
|---|---:|---|
| full_snapshot | 35.1942 s | Not measured |
| preparation | 35.3665 s | Not measured |
| first_frame | 0.5078 s | Not measured |
| total | 36.1138 s | Not measured |
| Full-snapshot lock calls | 528 | 1 by tested control flow; hardware measurement pending |
| Full-snapshot unlock calls | 528 | 1 by tested control flow; hardware measurement pending |
| Full-snapshot in-lock Flush calls | 0 | 2 by tested control flow; hardware measurement pending |

Before SDK totals: extended Unlock9.0941s/272, extended Lock9.0298s/272, normal Unlock8.4680s/256, normal Lock8.1410s/256. Their supplied rounded values sum to34.7329s (the attachment's34.7339s has a0.0010s arithmetic difference), approximately98.69% of full_snapshot. Initial OFF0.0199s, topology0.1239s, Python verification0.0175s and storage preparation are much smaller. This supports changing lock scope, not removing verification, altering TimeSlot or reusing a cached configuration.

### Vendor basis

Installed `4_Software_API.pdf` sections4.3.4.1-4.3.4.3, printed pages30-32, describe asynchronous parameter reads inside one communication lock. Pointer outputs can be written until Flush/Unlock completes; application buffers must remain valid. Flush can complete pending reads while retaining the lock. Unlock both completes communication and releases the link. eAcqDefault may enable pulsers depending on software defaults; the new batch uses explicit eAcqOff for BOTH lock and unlock. The same contract is in installed UTKernelDriver.h around617-629. No default-unlock software setting is changed.

Installed CustomizedDriverAPI.cpp `OEMPA_ReadHW` locks around1912, reads/Flushes topology before allocation, loops through every cycle around2213, calls normal and MultiHWChannel focal-law helpers and unlocks around2251. `ReadHWWriteFileMultiHWChannel` around1832 issues emission width/delay/aperture or receive-start/aperture/decimation reads under that caller-owned lock without acquiring its own. This directly supports multiple cycle indexes and MultiHWChannel parameter reads under one session. Raw getter bodies are SDK binaries, but the vendor's own call sites establish the intended lifecycle. No vendor code/manual is redistributed here.

### Candidate implementation

`bridge/fmc_batch_readback.h` is the shared template used by the real SDK adapter and an SDK-free deferred-output fake harness. It owns256 stable cycle records, including every scalar/enum/bitmap/array/count/capacity reference passed to getters. Nothing is resized while requests are pending. Under one OFF lock it reads CycleCount/MultiChannel, Flushes before inspecting topology, queues all256 normal and256 MultiHWChannel outputs, Flushes before any flag-dependent TX read, then reads the16 independently selected base-cycle TX records. The same additional conditional widths/delays are retained if a completed SDK flag actually supplies true. The documented unusable classification still decodes as unavailable, never False/hardware verified. Normal derived sampling/aperture decoding occurs after OFF unlock, as in the previous reader.

Only after all getters, both Flush calls, final OFF unlock and decoding succeed does the additive export copy outputs to the Python-owned arrays. Failures/throws attempt exactly one cleanup OFF unlock after a successful lock; no retry or partial publication. Lock failure queues nothing. Unlock failure is reported as failed snapshot, never Verified. A communication-failed/throwing SDK unlock cannot be proven to have released a real remote/driver lock by offline tests; state is uncertain and no acquisition may follow. Do not force unlock with guessed retries; normal disconnect/cleanup and diagnosis are required. Fixed buffer/count failures likewise reject. A failed native batch retains its single bounded output owner on OEMPAContext until that handle is destroyed; declaration order ensures outputs outlive the SDK device destructor. Further batches on that handle are refused until full teardown/new connection. This also protects deferred pointers if unlock fails before draining requests. Successful readback releases the owner only after completed OFF unlock/decoding/publication.

Python reuses the existing normal/extended decoders and field-assembly loop. All256 cycles and existing verifier comparisons/provenance are unchanged. Only exact approved full16x16 FMC with valid applied-file provenance opts into batching. Fresh in-batch topology must agree with the pre-read topology. A missing old-DLL export alone uses the complete legacy path; a supported export failure NEVER retries via legacy/cached data. A-scan/PA and other FMC shapes retain their original lock/readback paths. SettingId is not used. Both Apply Configuration and Acquire still perform full fresh verification; no dirty/stale/reconnect gate is weakened.

The full_snapshot now has one lock pair; initial safety OFF, separate topology_refresh, storage OFF and final acquisition OFF remain unchanged and visible as their own timing entries. Thus total preparation has more than one lock pair. Existing per-method detailed timing now includes FMCBatch.LockDevice/UnlockDevice/Flush/getters; aggregate logs still show only top-five SDK totals and metadata keeps every entry. Callback, first-frame, shutdown, raw data and mapping code are unchanged. Cancellation is checked before and after the synchronous native batch and during Python assembly; it cannot interrupt an SDK call. Closing must wait for worker cleanup, not destroy a held device.

### Offline validation and remaining measurements

The native fake defers output writes until Flush/Unlock and asserts OFF state and lock ownership on every hardware getter. It checks complete normal/MultiHW/TX coverage, expected logical fields and counts, SDK-unreadable outputs, functional flags, topology/capacity/sampling errors and lock/getter/flush/unlock false/exception cleanup and deferred writes surviving an uncertain failed unlock. Python tests compare complete legacy/batch HardwareSnapshot and VerificationReport evidence, late-cycle readable mismatch, no failure fallback, missing-export compatibility, topology change, cancellation and PA/noneligible isolation. Fake-ctypes tests check256 entries, output counts/order/types and unavailable values. Existing first-frame/native callback and dataset regressions remain required.

No hardware operation occurred and no speedup is claimed. Large-batch SDK/device behavior, queue capacity and timings still need the following controlled manual validation.

### Exact manual comparison procedure

1. Safely Stop, Disconnect and close all production GUIs. Build `cmd /c bridge\build_bridge.cmd` to deploy the current default DLL. `cmd /c bridge\build_bridge.cmd oempa_bridge_batch.dll` already builds a separate candidate without disturbing a loaded production DLL; runtime still uses oempa_bridge.dll.
2. Launch production GUI, connect to unchanged192.168.1.11:5001. Keep acquisition OFF. Apply unchanged/hash-matched configs/fmc16_full.txt through the existing safe path. Its full batch readback must reach Verified (mixed sources)/FMC-ready. Any SDK error, timeout or readable mismatch: STOP, no firing and no automatic legacy retry.
3. Only under explicit operator approval, perform ONE normal FMC acquisition with the same previous settings:256 logical cycles, MultiHWChannel enabled,20/0dB,0/30us,TimeSlot2000us,100MHz/3001points,Compression/Signed8-bit,filter1,unchanged width/aperture/mapping. Existing fresh acquisition preflight must pass again. Do not change settings to improve the comparison and do not automatically retry.
4. Verify unchanged first-frame acceptance,256 records/raw(256,actual N)/cube(16,16,actual N), dtype/timing/provenance. Keep physical firing count Unknown. Save only an accepted new dataset and sidecar, reload/check equality, then safely disconnect/close.
5. Compare full_snapshot/preparation/first_frame/total against the before table. Inspect timing_profile.preparation_sdk.off_readback.calls for FMCBatch.LockDevice count1,UnlockDevice count1,Flush count2 and all normal/MultiHW/base TX getter counts. On the current unusable classification SDK, widths and delays each have16 calls;256 per-cycle normal/MultiHW reads remain. Separate topology and OFF counts are additional, not missing. Report all timings and any diagnostic warnings. No B-scan/TFM acquisition/reconstruction is needed.
