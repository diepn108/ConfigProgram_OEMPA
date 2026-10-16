# Local experimental data

Raw acquisitions and metadata sidecars are intentionally not included in Git. Existing local datasets are preserved during cleanup, including the 18-mm experiment and historical FMC/PA records. They are not disposable merely because of their size or filename.

Copy a dataset together with its `.npy.json` sidecar to preserve captured timing, configuration identity and verification provenance. Legacy files without sidecars remain metadata-incomplete. The program must not guess their sampling frequency/start from current GUI settings.

Automated offline tests generate synthetic inputs in temporary directories; no lab dataset is required to run them.
