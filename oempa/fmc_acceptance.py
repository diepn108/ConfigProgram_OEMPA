"""Ordered immutable first-frame acceptance, independent of hardware/UI."""

from dataclasses import dataclass
from oempa.callback_order import FIELDS

FRAME_FIELDS = ('accepted_cycles', 'first_frame_complete', 'error', 'error_cycle', 'total_callbacks',
                'completion_arrival', 'first_post_frame_arrival', 'post_frame_callback_count',
                'pre_frame_duplicates', 'unexpected_pre_frame_callbacks', 'malformed_pre_frame_callbacks',
                'out_of_order_pre_frame_callbacks', 'unexpected_post_frame_callbacks', 'malformed_post_frame_callbacks')
REASONS = {1: 'malformed callback', 2: 'unexpected cycle', 3: 'duplicate cycle', 4: 'out-of-order cycle'}


def require_first_frame(frame, complete=False):
    accepted = frame['accepted_cycles']
    if not 0 <= accepted <= 256:
        raise RuntimeError('Invalid first-frame evidence')
    if frame['error']:
        raise RuntimeError(f"{REASONS.get(frame['error'], 'invalid callback')} {frame['error_cycle']} before first-frame completion")
    if any(frame[key] for key in ('pre_frame_duplicates', 'unexpected_pre_frame_callbacks', 'malformed_pre_frame_callbacks', 'out_of_order_pre_frame_callbacks')):
        raise RuntimeError('Invalid first-frame integrity counters')
    done = bool(frame['first_frame_complete'])
    if done != (accepted == 256) or (done and frame['completion_arrival'] != 256):
        raise RuntimeError('Inconsistent first-frame boundary')
    if complete and not done:
        raise RuntimeError(f"Incomplete first frame: {accepted}/256; missing cycles {list(range(accepted, 256))}")
    return done


@dataclass(frozen=True)
class FMCFrameEvidence:
    expected_cycles: int
    accepted_cycles: int
    first_frame_complete: bool
    first_frame_order_valid: bool
    missing_cycles: tuple[int, ...]
    pre_frame_duplicates: int
    unexpected_pre_frame_callbacks: int
    malformed_pre_frame_callbacks: int
    out_of_order_pre_frame_callbacks: int
    post_frame_callback_count: int
    unexpected_post_frame_callbacks: int
    malformed_post_frame_callbacks: int
    total_callbacks: int
    completion_arrival: int
    first_post_frame_arrival: int
    chronology_overflow: bool
    chronology_events: tuple[tuple[object, ...], ...]


def first_frame_evidence(frame, order):
    require_first_frame(frame, complete=True)
    callbacks = [event for event in order['events'] if event['kind'] == 'callback']
    if len(callbacks) < 256 or any(event['arrival_index'] != i + 1 or event['cycle_id'] != i or event['status'] for i, event in enumerate(callbacks[:256])):
        raise RuntimeError('Chronology does not prove the ordered valid first frame')
    if frame['total_callbacks'] != 256 + frame['post_frame_callback_count']:
        raise RuntimeError('Inconsistent post-frame counters')
    return FMCFrameEvidence(256, 256, True, True, (), 0, 0, 0, 0,
                            frame['post_frame_callback_count'], frame['unexpected_post_frame_callbacks'], frame['malformed_post_frame_callbacks'],
                            frame['total_callbacks'], frame['completion_arrival'], frame['first_post_frame_arrival'], order['overflow'],
                            tuple(tuple(event[field] for field in FIELDS) for event in order['events']))


def require_records(stats, complete=False):
    # Legacy aggregate diagnostic only; production acceptance uses the immutable frame boundary.
    counts = stats["cycle_counts"]
    missing = [index for index, count in enumerate(counts) if count == 0]
    duplicates = [index for index, count in enumerate(counts) if count > 1]
    if len(counts) != 256 or stats["duplicates"] or duplicates or stats["unexpected"] or stats["malformed"] or any(count < 0 for count in counts):
        raise RuntimeError(f"Callback sequence rejected: duplicates={duplicates}, unexpected={stats['unexpected']} (first {stats['first_unexpected']}), malformed={stats['malformed']}, missing={missing}")
    if complete and (missing or stats["total"] != 256 or tuple(counts) != (1,) * 256):
        raise RuntimeError(f"Incomplete callback sequence: total={stats['total']}, missing={missing}, duplicates={duplicates}")


class FMCFrameRejected(RuntimeError):
    def __init__(self, reason, stats, order, frame=None):
        self.callback_stats = stats
        self.callback_order = order
        arrivals = [event for event in order['events'] if event['kind'] == 'callback']
        first_complete = len(arrivals) >= 256 and all(event['cycle_id'] == i and not event['malformed'] for i, event in enumerate(arrivals[:256]))
        unique = sum(count > 0 for count in stats['cycle_counts'])
        self.complete_diagnostic = str(reason)
        if frame is not None:
            self.first_frame = frame
            RuntimeError.__init__(self, f"FMC first frame rejected\nRequired cycles: {frame['accepted_cycles']}/256\nReason: {str(reason)[:300]}\nDataset not accepted/saved")
            return
        super().__init__(f"FMC frame rejected\nComplete first sequence: {'Yes' if first_complete else 'Not proved'}\n"
                         f"Unique required cycles: {unique}/256\nAdditional/invalid callbacks: {stats['duplicates']} duplicate, "
                         f"{stats['unexpected']} unexpected, {stats['malformed']} malformed\n"
                         "Dataset not accepted/saved under current strict policy")
