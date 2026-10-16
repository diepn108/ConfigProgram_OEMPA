import time
from concurrent.futures import CancelledError

import numpy as np

from oempa import api


class AcquisitionResult:
    def __init__(
        self,
        scans,
        point_count,
        data_size,
        signed,
        bit_size,
    ):
        self.scans = scans
        self.point_count = point_count
        self.data_size = data_size
        self.signed = signed
        self.bit_size = bit_size

    @property
    def cycle_count(self):
        return self.scans.shape[0]

    @property
    def shape(self):
        return self.scans.shape


class OEMPAAcquisition:
    def __init__(self, device):
        self.device = device

        self._callback_registered = False
        self._acquisition_enabled = False

    # Setup

    def prepare(self, cycle_count=None, callback_capacity_bytes=None, timing=None):
        self._require_connection()

        if cycle_count is None:
            cycle_count = self.device.cycle_count

        cycle_count = int(cycle_count)

        if cycle_count <= 0:
            raise ValueError(
                "Cycle count must be greater than zero."
            )

        def observe(name, function, *args):
            return timing.call(name, function, *args) if timing is not None else function(*args)

        # Acquisition must be OFF before changing storage

        observe("storage_off", self.stop)

        observe("storage_set_count", api.set_multiascan_cycle_count,
            self.device.handle,
            cycle_count,
        )

        if not self._callback_registered:
            observe("storage_register_callback", api.register_ascan_callback,
                self.device.handle
            )

            self._callback_registered = True

        observe("storage_clear", api.clear_multiascan,
            self.device.handle
        )

        if callback_capacity_bytes is not None:
            observe("storage_allocate", api.prepare_ascan_callback_buffers, self.device.handle, callback_capacity_bytes)

        return cycle_count

    # Acquisition control

    def start(self):
        self._require_connection()

        if not self._callback_registered:
            raise RuntimeError(
                "Acquisition has not been prepared."
            )

        if self._acquisition_enabled:
            return

        api.enable_acquisition(
            self.device.handle
        )

        self._acquisition_enabled = True

    def stop(self):
        if not self.device.is_connected:
            self._acquisition_enabled = False
            return

        api.disable_acquisition(
            self.device.handle
        )

        self._acquisition_enabled = False

    # Acquisition

    def acquire(
        self,
        cycle_count=None,
        timeout_s=5.0,
        poll_interval_s=0.02,
        progress_callback=None,
        cancel_event=None,
        callback_capacity_bytes=None,
        prepared_callback=None,
        record_validator=None,
        poll_wait=None,
        timing=None,
    ):
        self._require_connection()

        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError("Acquisition cancelled before preparation.")

        if cycle_count is None:
            cycle_count = self.device.cycle_count

        if timing is None:
            cycle_count = self.prepare(cycle_count) if callback_capacity_bytes is None else self.prepare(cycle_count, callback_capacity_bytes=callback_capacity_bytes)
        else:
            with timing.sdk_preparation(api, 'storage'):
                cycle_count = self.prepare(cycle_count, callback_capacity_bytes=callback_capacity_bytes, timing=timing)

        start_time = time.monotonic()
        last_count = -1

        try:
            if prepared_callback is not None:
                timing.call("arm_chronology_and_frame", prepared_callback) if timing is not None else prepared_callback()
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError("Acquisition cancelled before starting.")
            if timing is not None:
                timing.mark('on_call_enter')
            self.start()
            if timing is not None:
                timing.mark('on_call_return')

            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise CancelledError("Acquisition cancelled.")
                received = api.get_multiascan_count(
                    self.device.handle
                )
                if record_validator is not None:
                    if record_validator(False) is True:
                        received = cycle_count

                if (
                    progress_callback is not None
                    and received != last_count
                ):
                    progress_callback(
                        received,
                        cycle_count,
                    )

                last_count = received

                if received >= cycle_count:
                    break

                elapsed = (
                    time.monotonic()
                    - start_time
                )

                if elapsed >= timeout_s:
                    break

                if poll_wait is not None:
                    poll_wait(poll_interval_s)
                elif cancel_event is None:
                    time.sleep(poll_interval_s)
                else:
                    cancel_event.wait(poll_interval_s)

        finally:
            if timing is not None:
                timing.mark('off_request')
            self.stop()
            if timing is not None:
                timing.mark('off_return')

        if record_validator is not None:
            record_validator(True)
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError("Acquisition cancelled after stopping.")

        received_cycles = self.get_received_cycles(
            cycle_count
        )

        if len(received_cycles) != cycle_count:
            missing = sorted(
                set(range(cycle_count))
                - set(received_cycles)
            )

            raise TimeoutError(
                f"Received "
                f"{len(received_cycles)}/"
                f"{cycle_count} cycles. "
                f"Missing cycles: {missing}"
            )

        result = self.read_cycles(
            cycle_count
        )
        if timing is not None:
            timing.mark('records_copied')
        return result

    # Stored data

    def get_received_count(self):
        self._require_connection()

        return api.get_multiascan_count(
            self.device.handle
        )

    def get_received_cycles(
        self,
        cycle_count=None,
    ):
        self._require_connection()

        if cycle_count is None:
            cycle_count = self.device.cycle_count

        received = []

        for cycle in range(
            int(cycle_count)
        ):
            if api.has_multiascan_cycle(
                self.device.handle,
                cycle,
            ):
                received.append(
                    cycle
                )

        return received

    def read_cycle(self, cycle):
        self._require_connection()

        raw_bytes, info = api.copy_multiascan(
            self.device.handle,
            cycle,
        )

        dtype = self._get_numpy_dtype(
            info["data_size"],
            info["signed"],
        )

        scan = np.frombuffer(
            raw_bytes,
            dtype=dtype,
        ).copy()

        if scan.size != info["point_count"]:
            raise RuntimeError(
                f"Cycle {cycle}: expected "
                f"{info['point_count']} samples, "
                f"but decoded {scan.size}."
            )

        return scan, info

    def read_cycles(
        self,
        cycle_count=None,
    ):
        self._require_connection()

        if cycle_count is None:
            cycle_count = self.device.cycle_count

        scans = []

        reference_info = None

        for cycle in range(
            int(cycle_count)
        ):
            scan, info = self.read_cycle(
                cycle
            )

            if reference_info is None:
                reference_info = info

            else:
                self._validate_info(
                    cycle,
                    reference_info,
                    info,
                )

            scans.append(
                scan
            )

        matrix = np.stack(
            scans,
            axis=0,
        )

        return AcquisitionResult(
            scans=matrix,
            point_count=reference_info[
                "point_count"
            ],
            data_size=reference_info[
                "data_size"
            ],
            signed=reference_info[
                "signed"
            ],
            bit_size=reference_info[
                "bit_size"
            ],
        )

    def clear(self):
        self._require_connection()

        self.stop()

        api.clear_multiascan(
            self.device.handle
        )

    # Validation

    def _validate_info(
        self,
        cycle,
        reference,
        current,
    ):
        fields = [
            "point_count",
            "data_size",
            "signed",
            "bit_size",
        ]

        for field in fields:
            if current[field] != reference[field]:
                raise RuntimeError(
                    f"Cycle {cycle}: "
                    f"{field}={current[field]}, "
                    f"expected "
                    f"{reference[field]}."
                )

    @staticmethod
    def _get_numpy_dtype(
        data_size,
        signed,
    ):
        if data_size == 1:
            if signed:
                return np.int8

            return np.uint8

        if data_size == 2:
            if signed:
                return np.int16

            return np.uint16

        raise RuntimeError(
            f"Unsupported A-scan data size: "
            f"{data_size} bytes."
        )

    def _require_connection(self):
        if not self.device.is_connected:
            raise RuntimeError(
                "OEM-PA is not connected."
            )
