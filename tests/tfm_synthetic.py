"""Deterministic point-reflector impulses for offline validation only."""

from dataclasses import replace
import math

import numpy as np

from oempa.dataset import AcquisitionDataset, AcquisitionMetadata
from oempa.hardware_state import CycleSnapshot, HardwareSnapshot


def synthetic_source(data, sampling_hz, start_s=0.0, revision=12):
    array = np.asarray(data)
    cycle = CycleSnapshot(0, start_s=start_s, sampling_hz=sampling_hz, point_count=array.shape[-1], range_s=(array.shape[-1] - 1) / sampling_hz)
    count = array.shape[0] * array.shape[1]
    hardware = HardwareSnapshot("FMC", count, True, True, tuple(replace(cycle, cycle=index) for index in range(count)))
    metadata = AcquisitionMetadata("FMC", array.shape, array.dtype.str, hardware=hardware, configuration_revision=revision, complete=True, axis_names=("TX", "RX", "sample"), buffer_source="Synthetic validation impulses; not hardware acquisition")
    return AcquisitionDataset(array, metadata)


def point_reflector(element_count, pitch_m, velocity_m_s, x_m, z_m, sampling_hz, start_s=0.0, sample_count=2048):
    data = np.zeros((element_count, element_count, sample_count), dtype=np.float64)
    positions = [(index - (element_count - 1) / 2) * pitch_m for index in range(element_count)]
    for tx in range(element_count):
        for rx in range(element_count):
            time_s = (math.hypot(x_m - positions[tx], z_m) + math.hypot(x_m - positions[rx], z_m)) / velocity_m_s
            position = (time_s - start_s) * sampling_hz
            if 0 <= position <= sample_count - 1:
                data[tx, rx, math.floor(position + 0.5)] = 1
    return synthetic_source(data, sampling_hz, start_s)
