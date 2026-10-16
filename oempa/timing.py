"""Bounded per-attempt FMC timing observations; never controls the device."""

from dataclasses import dataclass, field
import time
from contextlib import contextmanager


NATIVE_MARKS = ('sdk_on_enter', 'sdk_on_return', 'first_callback', 'frame_complete',
                'native_off_request', 'sdk_off_enter', 'sdk_off_return')
STAGES = {
    'worker_queue': ('requested', 'worker_start'),
    'preflight_readback': ('worker_start', 'preflight_readback_done'),
    'preflight_verification': ('preflight_readback_done', 'preflight_verified'),
    'storage_preparation': ('preflight_verified', 'on_call_enter'),
    'preparation': ('worker_start', 'on_call_enter'),
    'preparation_to_sdk_on': ('worker_start', 'sdk_on_enter'),
    'on_lock_overhead': ('on_call_enter', 'sdk_on_enter'),
    'on_call': ('on_call_enter', 'on_call_return'),
    'sdk_on': ('sdk_on_enter', 'sdk_on_return'),
    'first_callback_latency': ('sdk_on_enter', 'first_callback'),
    'first_frame': ('first_callback', 'frame_complete'),
    'worker_stop_latency': ('frame_complete', 'off_request'),
    'shutdown_off': ('off_request', 'off_return'),
    'sdk_off': ('sdk_off_enter', 'sdk_off_return'),
    'record_copy_validation': ('off_return', 'records_copied'),
    'cube_construction': ('records_copied', 'cube_built'),
    'metadata_verification': ('cube_built', 'metadata_verified'),
    'gui_delivery': ('metadata_verified', 'gui_delivered'),
    'gui_update': ('gui_delivered', 'gui_update_done'),
    'gui_render': ('gui_delivered', 'draw_complete'),
    'total': ('requested', 'draw_complete'),
    'worker_total': ('worker_start', 'metadata_verified'),
}


@dataclass
class FMCTiming:
    marks: dict = field(default_factory=dict)
    counters: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    native: dict = field(default_factory=dict)
    preparation: dict = field(default_factory=dict)
    preparation_sdk: dict = field(default_factory=dict)

    @contextmanager
    def measure(self, name):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.preparation[name] = time.perf_counter() - start

    def call(self, name, function, *args, **kwargs):
        with self.measure(name):
            return function(*args, **kwargs)

    @contextmanager
    def sdk_preparation(self, reader, phase):
        active = False
        try:
            reader.begin_preparation_timing()
            active = True
        except (AttributeError, RuntimeError, OSError) as exc:
            self.warnings.append(f'Preparation SDK timings unavailable: {exc}')
        try:
            yield
        finally:
            if active:
                try:
                    self.preparation_sdk[phase] = reader.end_preparation_timing()
                    if self.preparation_sdk[phase]['overflow']:
                        self.warnings.append('Preparation SDK timing capacity exceeded')
                except (AttributeError, RuntimeError, OSError) as exc:
                    self.warnings.append(f'Preparation SDK timings unavailable: {exc}')


    def mark(self, name, value=None):
        self.marks.setdefault(name, time.perf_counter() if value is None else value)

    def native_marks(self, observation):
        self.native = observation
        # Current Windows Python uses QPC; other clocks must not be silently aligned.
        if 'QueryPerformanceCounter' not in time.get_clock_info('perf_counter').implementation:
            self.warnings.append('Native QPC/Python clock alignment unavailable')
            return
        frequency = observation['frequency']
        if frequency <= 0:
            self.warnings.append('Native QPC frequency unavailable')
            return
        for name in NATIVE_MARKS:
            if observation[name] > 0:
                self.mark(name, observation[name] / frequency)

    def report(self):
        durations = {}
        for name, (start, end) in STAGES.items():
            if start in self.marks and end in self.marks:
                value = self.marks[end] - self.marks[start]
                if value >= 0:
                    durations[name] = value
        return {'clock': 'time.perf_counter / Windows QPC', 'marks': dict(self.marks),
                'durations_s': durations, 'counters': dict(self.counters),
                'native_qpc': dict(self.native), 'warnings': tuple(self.warnings),
                'preparation_stages_s': dict(self.preparation), 'preparation_sdk': dict(self.preparation_sdk),
                'physical_firing_count': 'Unknown'}

    def summary(self):
        durations = self.report()['durations_s']
        keys = ('preparation', 'sdk_on', 'first_callback_latency', 'first_frame', 'shutdown_off',
                'record_copy_validation', 'cube_construction', 'metadata_verification', 'gui_render', 'total')
        summary = '[TIMING] FMC ' + '; '.join(f'{key}={durations[key]:.4f}s' for key in keys if key in durations)
        if self.preparation:
            summary += '; preparation stages: ' + ', '.join(f'{key}={value:.4f}s' for key, value in self.preparation.items())
        slow = [(value['total_s'], phase + '.' + name, value['count']) for phase, result in self.preparation_sdk.items() for name, value in result['calls'].items()]
        if slow:
            summary += '; top SDK totals: ' + ', '.join(f'{name}={seconds:.4f}s/{count} calls' for seconds, name, count in sorted(slow, reverse=True)[:5])
        return summary
