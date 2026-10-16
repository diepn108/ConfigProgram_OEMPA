"""Main-thread application state, separate from draft values and hardware objects."""

from dataclasses import dataclass
from enum import StrEnum


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


class Operation(StrEnum):
    IDLE = "idle"
    CONNECTING = "connecting"
    APPLYING = "applying"
    ACQUIRING = "acquiring"
    LOADING = "loading"
    RECONSTRUCTING = "reconstructing"
    STOPPING = "stopping"
    DISCONNECTING = "disconnecting"
    SHUTDOWN = "shutdown"
    ERROR = "error"


class ConfigurationState(StrEnum):
    UNKNOWN = "unknown"
    DIRTY = "dirty"
    INVALID = "invalid"
    APPLIED = "applied"


@dataclass
class ApplicationState:
    connection: ConnectionState = ConnectionState.DISCONNECTED
    operation: Operation = Operation.IDLE
    configuration: ConfigurationState = ConfigurationState.UNKNOWN
    draft_revision: int = 0
    applied_revision: int | None = None
    readback_verified: bool = False
    configuration_verified: bool = False
    field_verification: tuple = ()
    verification_scope: str = ""
    draft_valid: bool = False
    hardware_modes: frozenset[str] = frozenset({"A-scan", "FMC", "PA"})
    configuration_modes: frozenset[str] | None = None
    mode: str = "FMC"
    applied_mode: str | None = None
    dataset_revision: int | None = None
    dataset_mode: str | None = None
    dataset_stale: bool = False
    closing: bool = False
    shutdown_complete: bool = False
    error: str | None = None
    status: str = "Disconnected"
    actual_snapshot: object = None
    requested_configuration: object = None
    verification_mismatches: tuple[str, ...] = ()

    @property
    def acquisition_ready(self):
        return (
            self.connection == ConnectionState.CONNECTED
            and self.operation == Operation.IDLE
            and self.configuration == ConfigurationState.APPLIED
            and self.draft_valid and (self.readback_verified or self.configuration_verified)
            and self.applied_revision == self.draft_revision
            and self.applied_mode == self.mode
            and self.mode in self.hardware_modes
            and not self.closing and self.error is None
        )

    @property
    def editable(self):
        return self.operation in {Operation.IDLE, Operation.ERROR} and not self.closing

    @property
    def apply_ready(self):
        modes = self.hardware_modes if self.configuration_modes is None else self.configuration_modes
        return self.editable and self.connection == ConnectionState.CONNECTED and self.draft_valid and self.mode in modes

    @property
    def configuration_label(self):
        if self.verification_mismatches:
            return "Mismatch / Unknown"
        if self.configuration == ConfigurationState.APPLIED:
            if self.configuration_verified and not self.readback_verified:
                return "Verified (mixed sources)"
            return "Verified" if self.readback_verified else "Applied / Unverified"
        return self.configuration.value.capitalize()

    @property
    def dataset_label(self):
        if self.dataset_revision is None and self.dataset_mode is None:
            return "None"
        return "Stale" if self.dataset_stale else "Current"

    def edit_configuration(self, valid=False):
        if self.operation not in {Operation.IDLE, Operation.ERROR} or self.closing:
            raise RuntimeError("Configuration cannot change during an operation.")
        self.draft_revision += 1
        self.draft_valid = valid
        self.configuration = ConfigurationState.DIRTY if valid else ConfigurationState.INVALID
        self.invalidate_dataset()
        self.status = "Configuration dirty; apply required"

    def set_mode(self, mode):
        if mode not in {"A-scan", "FMC", "PA"}:
            raise ValueError("Unknown acquisition mode.")
        if mode != self.mode:
            self.edit_configuration(self.draft_valid)
            self.mode = mode

    def invalidate_dataset(self):
        if self.dataset_revision is not None:
            self.dataset_stale = True

    def begin(self, operation):
        if self.closing and operation != Operation.SHUTDOWN:
            raise RuntimeError("Application is closing.")
        if self.operation not in {Operation.IDLE, Operation.ERROR}:
            raise RuntimeError("Another operation owns the application.")
        if operation == Operation.ACQUIRING and not self.acquisition_ready:
            raise RuntimeError("Acquisition requires connected, applied, verified configuration.")
        if operation == Operation.APPLYING:
            if not self.apply_ready:
                raise RuntimeError("Apply requires a connection and valid draft.")
            self.configuration = ConfigurationState.UNKNOWN
            self.readback_verified = False
            self.configuration_verified = False
            self.invalidate_dataset()
        if operation == Operation.CONNECTING:
            if self.connection != ConnectionState.DISCONNECTED:
                raise RuntimeError("Disconnect/recover before connecting again.")
            self.connection = ConnectionState.CONNECTING
            self.forget_applied()
        if operation == Operation.DISCONNECTING:
            self.connection = ConnectionState.DISCONNECTING
            self.forget_applied()
        self.operation = operation
        self.error = None
        self.status = operation.value.capitalize()

    def forget_applied(self):
        self.applied_revision = None
        self.applied_mode = None
        self.readback_verified = False
        self.configuration_verified = False
        self.field_verification = ()
        self.verification_scope = ""
        self.configuration = ConfigurationState.UNKNOWN
        self.invalidate_dataset()

    def complete(self, operation, revision, mode, result):
        if result.connected is not None:
            self.connection = ConnectionState.CONNECTED if result.connected else ConnectionState.DISCONNECTED
        if operation == Operation.APPLYING:
            if result.verification is not None:
                self.actual_snapshot = result.verification.snapshot
                self.verification_mismatches = tuple(str(item) for item in result.verification.mismatches)
                self.field_verification = result.verification.field_verification
            else:
                self.verification_mismatches = ()
            self.requested_configuration = result.requested_configuration
            self.applied_revision = revision
            self.applied_mode = mode
            report_ok = result.verification is None or result.verification.verified
            self.readback_verified = result.readback_verified and not self.verification_mismatches and report_ok
            self.configuration_verified = result.configuration_verified and result.verification is not None and result.verification.verified
            self.verification_scope = result.verification_scope
            self.configuration = ConfigurationState.APPLIED if revision == self.draft_revision else ConfigurationState.DIRTY
        elif operation == Operation.ACQUIRING:
            if result.verification is not None:
                self.actual_snapshot = result.verification.snapshot
            self.dataset_revision = revision
            self.dataset_mode = mode
            self.dataset_stale = revision != self.draft_revision or mode != self.mode
        elif operation in {Operation.DISCONNECTING, Operation.SHUTDOWN}:
            self.forget_applied()
        self.operation = Operation.IDLE
        self.status = result.status or f"{operation.value.capitalize()} completed"
        self.error = None
        if operation == Operation.SHUTDOWN:
            self.shutdown_complete = True

    def fail(self, operation, message):
        if operation not in {Operation.LOADING, Operation.RECONSTRUCTING}:
            self.forget_applied()
        verification = getattr(message, "verification", None)
        if verification is not None:
            self.actual_snapshot = verification.snapshot
            self.field_verification = verification.field_verification
            self.requested_configuration = message.requested_configuration
            self.verification_mismatches = tuple(str(item) for item in verification.mismatches)
        if operation in {Operation.CONNECTING, Operation.DISCONNECTING, Operation.SHUTDOWN}:
            self.connection = ConnectionState.ERROR
        self.operation = Operation.ERROR
        self.error = str(message)
        self.status = str(message)

    def cancelled(self, operation):
        if operation == Operation.APPLYING:
            self.forget_applied()
        if operation in {Operation.CONNECTING, Operation.DISCONNECTING, Operation.SHUTDOWN}:
            self.connection = ConnectionState.ERROR
            self.forget_applied()
        self.operation = Operation.IDLE
        self.status = f"{operation.value.capitalize()} cancelled"
