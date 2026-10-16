"""Serialized worker ownership with main-thread event consumption."""

from dataclasses import dataclass
from queue import Empty, Queue
import threading

from ui.state import ApplicationState, Operation


class OperationCancelled(Exception):
    """Raised at a cooperative cancellation boundary, after backend cleanup."""


@dataclass(frozen=True)
class OperationResult:
    payload: object = None
    connected: bool | None = None
    readback_verified: bool = False
    verification_scope: str = ""
    status: str = ""
    verification: object = None
    requested_configuration: object = None
    configuration_verified: bool = False


class OperationError(str):
    def __new__(cls, message, verification=None, requested_configuration=None):
        value = super().__new__(cls, message)
        value.verification = verification
        value.requested_configuration = requested_configuration
        return value


@dataclass(frozen=True)
class ControllerEvent:
    operation_id: int
    operation: Operation
    revision: int
    mode: str
    kind: str
    payload: object = None


class WorkerContext:
    def __init__(self, cancel_event, emit, revision=None, mode=None):
        self.cancel_event = cancel_event
        self._emit = emit
        self.revision = revision
        self.mode = mode

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise OperationCancelled("Operation cancelled")

    def progress(self, received, total):
        self._emit("progress", (received, total))


class OperationController:
    """Create and consume on the Tk thread; tasks receive no Tk objects.

    A task returns only after its resources are safe. Errors during cleanup must
    propagate as errors, never be reported as successful cancellation/shutdown.
    Ownership is retained until the terminal event is consumed and the worker
    has exited. Shutdown cleanup runs as the next serialized worker operation.
    """

    def __init__(self, state=None):
        self.state = state if state is not None else ApplicationState()
        self.events = Queue()
        self._owner_thread = threading.get_ident()
        self._thread = None
        self._active = None
        self._next_id = 0
        self._cancel = threading.Event()
        self._shutdown_task = None

    def _require_main_thread(self):
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("Controller state/events must be used on the main thread.")

    @property
    def active(self):
        return self._active is not None

    def submit(self, operation, task):
        self._require_main_thread()
        operation = Operation(operation)
        if operation in {Operation.IDLE, Operation.ERROR, Operation.STOPPING}:
            raise ValueError("Not a executable operation.")
        if self.active:
            raise RuntimeError("Another operation owns the controller.")
        self.state.begin(operation)
        self._next_id += 1
        identity = (self._next_id, operation, self.state.draft_revision, self.state.mode)
        self._active = identity
        self._cancel = threading.Event()

        def emit(kind, payload=None):
            self.events.put(ControllerEvent(*identity, kind, payload))

        context = WorkerContext(self._cancel, emit, identity[2], identity[3])

        def run():
            try:
                result = task(context)
                if not isinstance(result, OperationResult):
                    raise TypeError("Worker must return OperationResult.")
                emit("completed", result)
            except OperationCancelled as exc:
                emit("cancelled", str(exc))
            except Exception as exc:
                emit("error", OperationError(f"{type(exc).__name__}: {exc}", getattr(exc, "verification", None), getattr(exc, "requested_configuration", None)))

        self._thread = threading.Thread(target=run, name=f"OEMPA-{operation.value}", daemon=False)
        try:
            self._thread.start()
        except Exception as exc:
            self._active = None
            self.state.fail(operation, str(exc))
            raise
        return identity[0]

    def cancel(self):
        self._require_main_thread()
        if self.active:
            self._cancel.set()
            self.state.operation = Operation.STOPPING
            self.state.status = "Stopping; waiting for worker cleanup"

    def request_shutdown(self, cleanup):
        self._require_main_thread()
        self.state.closing = True
        self._shutdown_task = cleanup
        if self.active:
            self.cancel()
        else:
            self._start_shutdown()

    def _start_shutdown(self):
        task = self._shutdown_task
        self._shutdown_task = None
        self.submit(Operation.SHUTDOWN, task)

    def drain_events(self, limit=100):
        self._require_main_thread()
        accepted = []
        for _ in range(limit):
            try:
                event = self.events.get_nowait()
            except Empty:
                break
            if self._active is None or event.operation_id != self._active[0]:
                continue
            if event.kind in {"completed", "cancelled", "error"}:
                if self._thread.is_alive():
                    self.events.put(event)
                    break
                self._active = None
                if event.kind == "completed":
                    self.state.complete(event.operation, event.revision, event.mode, event.payload)
                elif event.kind == "cancelled":
                    self.state.cancelled(event.operation)
                else:
                    self.state.fail(event.operation, event.payload)
            accepted.append(event)
        if not self.active and self._shutdown_task is not None:
            self._start_shutdown()
        return accepted
