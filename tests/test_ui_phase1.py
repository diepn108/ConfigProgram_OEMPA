"""Offline tests only: standard-library fake tasks, no OEM-PA imports."""

import sys
import threading
import time
import unittest

from ui.controller import ControllerEvent, OperationController, OperationResult
from ui.state import ApplicationState, ConfigurationState, ConnectionState, Operation


def drain_until_idle(controller):
    events = []
    deadline = time.monotonic() + 3
    while controller.active and time.monotonic() < deadline:
        events.extend(controller.drain_events())
        time.sleep(0.001)
    if controller.active:
        raise AssertionError("Fake worker did not finish")
    return events


class FakeBackend:
    def __init__(self):
        self.calls = []

    def connect(self, context):
        self.calls.append(("connect", threading.get_ident()))
        return OperationResult(connected=True)

    def apply(self, context):
        self.calls.append(("apply", threading.get_ident()))
        return OperationResult(readback_verified=True, verification_scope="fake full readback")

    def acquire(self, context):
        self.calls.append(("acquire", threading.get_ident()))
        context.progress(1, 1)
        return OperationResult(payload="fake waveform")

    def close(self, context):
        self.calls.append(("close", threading.get_ident()))
        return OperationResult(connected=False)


class StateTests(unittest.TestCase):
    def ready_state(self):
        state = ApplicationState(connection=ConnectionState.CONNECTED)
        state.edit_configuration(valid=True)
        state.begin(Operation.APPLYING)
        state.complete(Operation.APPLYING, state.draft_revision, state.mode, OperationResult(readback_verified=True))
        return state

    def test_valid_draft_disconnected_is_blocked(self):
        state = ApplicationState()
        state.edit_configuration(valid=True)
        self.assertFalse(state.acquisition_ready)
        with self.assertRaises(RuntimeError):
            state.begin(Operation.ACQUIRING)

    def test_connected_unapplied_is_blocked(self):
        state = ApplicationState(connection=ConnectionState.CONNECTED, draft_valid=True)
        self.assertFalse(state.acquisition_ready)

    def test_apply_with_readback_is_ready(self):
        state = self.ready_state()
        self.assertTrue(state.acquisition_ready)
        self.assertEqual(state.configuration, ConfigurationState.APPLIED)
        self.assertEqual(state.applied_revision, state.draft_revision)

    def test_unverified_apply_is_blocked(self):
        state = self.ready_state()
        state.begin(Operation.APPLYING)
        state.complete(Operation.APPLYING, state.draft_revision, state.mode, OperationResult())
        self.assertFalse(state.readback_verified)
        self.assertFalse(state.acquisition_ready)

    def test_edit_keeps_historical_applied_revision_but_blocks_and_stales(self):
        state = self.ready_state()
        state.begin(Operation.ACQUIRING)
        state.complete(Operation.ACQUIRING, state.draft_revision, state.mode, OperationResult())
        old_revision = state.applied_revision
        state.edit_configuration(valid=True)
        self.assertEqual(state.configuration, ConfigurationState.DIRTY)
        self.assertEqual(state.applied_revision, old_revision)
        self.assertNotEqual(state.applied_revision, state.draft_revision)
        self.assertTrue(state.dataset_stale)
        self.assertFalse(state.acquisition_ready)

    def test_invalid_draft_blocks_apply(self):
        state = self.ready_state()
        state.edit_configuration(valid=False)
        with self.assertRaises(RuntimeError):
            state.begin(Operation.APPLYING)

    def test_edits_blocked_during_acquisition(self):
        state = self.ready_state()
        state.begin(Operation.ACQUIRING)
        with self.assertRaises(RuntimeError):
            state.edit_configuration(True)

    def test_mode_change_requires_apply(self):
        state = self.ready_state()
        state.set_mode("PA")
        self.assertFalse(state.acquisition_ready)
        self.assertEqual(state.applied_mode, "FMC")

    def test_partial_apply_failure_forgets_hardware_truth(self):
        state = self.ready_state()
        state.begin(Operation.APPLYING)
        state.fail(Operation.APPLYING, "partial write")
        self.assertEqual(state.configuration, ConfigurationState.UNKNOWN)
        self.assertIsNone(state.applied_revision)
        self.assertFalse(state.acquisition_ready)
        self.assertEqual(state.error, "partial write")

    def test_error_blocks_even_previously_verified_configuration(self):
        state = self.ready_state()
        state.error = "stop failed"
        self.assertFalse(state.acquisition_ready)

    def test_stale_revision_completion_does_not_enable_acquisition(self):
        state = self.ready_state()
        state.complete(Operation.APPLYING, state.draft_revision - 1, state.mode, OperationResult(readback_verified=True))
        self.assertFalse(state.acquisition_ready)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.controller = OperationController()

    def connect_and_apply(self):
        self.controller.submit(Operation.CONNECTING, self.backend.connect)
        drain_until_idle(self.controller)
        self.controller.state.edit_configuration(True)
        self.controller.submit(Operation.APPLYING, self.backend.apply)
        drain_until_idle(self.controller)

    def test_disconnected_to_connected_main_thread_consumes(self):
        owner = threading.get_ident()
        self.controller.submit(Operation.CONNECTING, self.backend.connect)
        self.assertEqual(self.controller.state.connection, ConnectionState.CONNECTING)
        events = drain_until_idle(self.controller)
        self.assertEqual(self.controller.state.connection, ConnectionState.CONNECTED)
        self.assertEqual(events[-1].kind, "completed")
        self.assertNotEqual(self.backend.calls[0][1], owner)
        self.assertFalse(self.controller.state.acquisition_ready)

    def test_apply_then_acquire_events_and_dataset(self):
        self.connect_and_apply()
        self.assertTrue(self.controller.state.acquisition_ready)
        self.controller.submit(Operation.ACQUIRING, self.backend.acquire)
        events = drain_until_idle(self.controller)
        self.assertEqual([event.kind for event in events], ["progress", "completed"])
        self.assertEqual(events[0].payload, (1, 1))
        self.assertEqual(self.controller.state.dataset_revision, self.controller.state.applied_revision)
        self.assertFalse(self.controller.state.dataset_stale)

    def test_only_one_owner_even_when_worker_finished_but_event_unconsumed(self):
        self.controller.submit(Operation.CONNECTING, self.backend.connect)
        with self.assertRaises(RuntimeError):
            self.controller.submit(Operation.CONNECTING, self.backend.connect)
        drain_until_idle(self.controller)

    def test_blocked_acquisition_does_not_start_worker(self):
        with self.assertRaises(RuntimeError):
            self.controller.submit(Operation.ACQUIRING, self.backend.acquire)
        self.assertEqual(self.backend.calls, [])
        self.assertFalse(self.controller.active)

    def test_dirty_configuration_blocks_controller_acquisition(self):
        self.connect_and_apply()
        self.controller.state.edit_configuration(True)
        with self.assertRaises(RuntimeError):
            self.controller.submit(Operation.ACQUIRING, self.backend.acquire)

    def test_partial_connection_error_requires_recovery(self):
        def failed(context):
            raise RuntimeError("partially connected")
        self.controller.submit(Operation.CONNECTING, failed)
        events = drain_until_idle(self.controller)
        self.assertEqual(events[-1].kind, "error")
        self.assertEqual(self.controller.state.connection, ConnectionState.ERROR)
        self.assertFalse(self.controller.state.acquisition_ready)
        self.controller.submit(Operation.DISCONNECTING, self.backend.close)
        drain_until_idle(self.controller)
        self.assertEqual(self.controller.state.connection, ConnectionState.DISCONNECTED)

    def test_apply_error_invalidates_previous_configuration(self):
        self.connect_and_apply()
        def failed(context):
            raise RuntimeError("partial apply")
        self.controller.submit(Operation.APPLYING, failed)
        drain_until_idle(self.controller)
        self.assertEqual(self.controller.state.operation, Operation.ERROR)
        self.assertFalse(self.controller.state.acquisition_ready)
        self.assertFalse(self.controller.state.readback_verified)

    def test_cancel_cleanup_precedes_terminal_event(self):
        self.connect_and_apply()
        started = threading.Event()
        cleaned = threading.Event()
        def acquire(context):
            try:
                started.set()
                context.cancel_event.wait(2)
                context.check_cancelled()
            finally:
                cleaned.set()
        self.controller.submit(Operation.ACQUIRING, acquire)
        self.assertTrue(started.wait(1))
        self.controller.cancel()
        self.assertEqual(self.controller.state.operation, Operation.STOPPING)
        events = drain_until_idle(self.controller)
        self.assertTrue(cleaned.is_set())
        self.assertEqual(events[-1].kind, "cancelled")
        self.assertEqual(self.controller.state.operation, Operation.IDLE)

    def test_shutdown_waits_for_owner_then_closes(self):
        self.connect_and_apply()
        order = []
        started = threading.Event()
        def acquire(context):
            try:
                order.append("acquire")
                started.set()
                context.cancel_event.wait(2)
                context.check_cancelled()
            finally:
                order.append("stopped")
        def cleanup(context):
            order.append("destroy")
            return OperationResult(connected=False)
        self.controller.submit(Operation.ACQUIRING, acquire)
        self.assertTrue(started.wait(1))
        self.controller.request_shutdown(cleanup)
        with self.assertRaises(RuntimeError):
            self.controller.submit(Operation.APPLYING, self.backend.apply)
        drain_until_idle(self.controller)
        self.assertEqual(order, ["acquire", "stopped", "destroy"])
        self.assertTrue(self.controller.state.shutdown_complete)
        self.assertFalse(self.controller.state.acquisition_ready)

    def test_shutdown_during_blocking_connect_waits_without_force_kill(self):
        started = threading.Event()
        release = threading.Event()
        def connect(context):
            started.set()
            release.wait(2)
            return OperationResult(connected=True)
        self.controller.submit(Operation.CONNECTING, connect)
        self.assertTrue(started.wait(1))
        self.controller.request_shutdown(self.backend.close)
        self.controller.drain_events()
        self.assertTrue(self.controller.active)
        self.assertEqual(self.backend.calls, [])
        release.set()
        drain_until_idle(self.controller)
        self.assertTrue(self.controller.state.shutdown_complete)

    def test_shutdown_failure_keeps_window_state_open_for_retry(self):
        def failed(context):
            raise RuntimeError("stop failed")
        self.controller.request_shutdown(failed)
        drain_until_idle(self.controller)
        self.assertFalse(self.controller.state.shutdown_complete)
        self.assertTrue(self.controller.state.closing)
        self.assertFalse(self.controller.state.acquisition_ready)
        self.controller.request_shutdown(self.backend.close)
        drain_until_idle(self.controller)
        self.assertTrue(self.controller.state.shutdown_complete)

    def test_cleanup_failure_is_error_not_cancellation(self):
        self.connect_and_apply()
        started = threading.Event()
        def acquire(context):
            try:
                started.set()
                context.cancel_event.wait(2)
                context.check_cancelled()
            finally:
                raise RuntimeError("OFF failed")
        self.controller.submit(Operation.ACQUIRING, acquire)
        self.assertTrue(started.wait(1))
        self.controller.cancel()
        events = drain_until_idle(self.controller)
        self.assertEqual(events[-1].kind, "error")
        self.assertFalse(self.controller.state.acquisition_ready)

    def test_non_main_thread_cannot_drain_or_submit(self):
        errors = []
        def worker():
            for action in (self.controller.drain_events, lambda: self.controller.submit(Operation.CONNECTING, self.backend.connect)):
                try:
                    action()
                except RuntimeError as exc:
                    errors.append(str(exc))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(1)
        self.assertEqual(len(errors), 2)

    def test_stale_event_ignored(self):
        self.controller.events.put(ControllerEvent(999, Operation.CONNECTING, 0, "FMC", "completed", OperationResult(connected=True)))
        self.assertEqual(self.controller.drain_events(), [])
        self.assertEqual(self.controller.state.connection, ConnectionState.DISCONNECTED)

    def test_import_does_not_load_sdk(self):
        self.assertNotIn("oempa.api", sys.modules)
        self.assertNotIn("oempa.driver", sys.modules)


if __name__ == "__main__":
    unittest.main()
