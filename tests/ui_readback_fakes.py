"""Reusable complete software-only readback fixtures; no native imports."""

from oempa.hardware_state import CycleSnapshot, HardwareSnapshot


def matching_fmc(config, sampling_hz=50e6):
    cycles = []
    for index in range(config.cycle_count):
        tx, rx = divmod(index, config.rx_count)
        is_hw = rx == 0
        cycles.append(CycleSnapshot(
            cycle=index, start_s=0.0, normal_ascan_start_s=0.0, range_s=config.range_us * 1e-6,
            point_count=round(config.range_us * 1e-6 * sampling_hz) + 1, point_factor=256,
            sampling_hz=sampling_hz, compression_type=0, bit_size=0, rectification=0,
            gain_analog_db=config.analog_gain_db if is_hw else 0.0,
            gain_digital_db=config.digital_gain_db, beam_correction_db=config.beam_correction_db,
            filter_index=config.filter_index, time_slot_s=config.time_slot_us * 1e-6,
            tx_aperture=(tx,) if is_hw else (), rx_aperture=(rx,),
            widths_s=(config.pulser_width_us * 1e-6,) if is_hw else (),
            tx_delays_s=(0.0,) if is_hw else (), hw_acquisition=is_hw,
            multi_starts_s=(0.0,) * config.rx_count, multi_decimation_bytes=(0,) * 8,
        ))
    return HardwareSnapshot("FMC", config.cycle_count, True, True, tuple(cycles))


class FakeReadbackAPI:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def get_configuration_diagnostic(self):
        return {"entered": True, "before_hw": True, "after_hw": True, "left": True, "parsed_cycle_count": self.snapshot.cycle_count}

    def get_cycle_snapshot(self, handle, index):
        self.calls.append(("cycle", index))
        cycle = self.snapshot.cycles[index]
        names = ("start_s", "range_s", "point_count", "point_factor", "sampling_hz", "compression_type",
                 "bit_size", "rectification", "gain_analog_db", "gain_digital_db", "beam_correction_db", "filter_index", "time_slot_s")
        result = {name: getattr(cycle, name) for name in names}
        result["start_s"] = cycle.normal_ascan_start_s
        result["tx_enabled"] = None if cycle.tx_aperture is None else [int(i in cycle.tx_aperture) for i in range(16)]
        result["rx_enabled"] = None if cycle.rx_aperture is None else [int(i in cycle.rx_aperture) for i in range(16)]
        return result

    def get_extended_cycle_snapshot(self, handle, index, multi_channel=False):
        self.calls.append(("extended", index))
        cycle = self.snapshot.cycles[index]
        return {name: getattr(cycle, name) for name in ("widths_s", "tx_delays_s", "hw_acquisition", "multi_starts_s", "multi_decimation_bytes")}

    def get_pa_delay_snapshot(self, handle, index):
        cycle = self.snapshot.cycles[index]
        return {name: getattr(cycle, name) for name in ("tx_delays_s", "rx_delays_s", "rx_focusing")}

    def get_pa_receive_snapshot(self, handle, index):
        cycle = self.snapshot.cycles[index]
        return {"gains_db": cycle.receive_gains_db, "focal_tof_s": cycle.focal_tof_s, "ddf_enabled": cycle.ddf_enabled,
                "emission_wedge_delay_s": cycle.emission_wedge_delay_s, "reception_wedge_delay_s": cycle.reception_wedge_delay_s}
