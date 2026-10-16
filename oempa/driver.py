from oempa import api


class OEMPADevice:
    def __init__(
        self,
        ip_address="192.168.1.11",
        port=5001,
    ):
        self.ip_address = ip_address
        self.port = int(port)

        self._handle = None
        self._connected = False

        self._cycle_count = 0
        self._multichannel_supported = False
        self._multichannel_enabled = False

    # Properties

    @property
    def is_connected(self):
        return self._connected

    @property
    def cycle_count(self):
        return self._cycle_count

    @property
    def multichannel_supported(self):
        return self._multichannel_supported

    @property
    def multichannel_enabled(self):
        return self._multichannel_enabled

    @property
    def handle(self):
        if self._handle is None:
            raise RuntimeError(
                "OEM-PA device handle has not been created."
            )

        return self._handle

    # Device lifecycle

    def open(self):
        if self._handle is not None:
            return

        self._handle = api.create_handle()

    def close(self):
        if self._handle is None:
            return

        if self._connected:
            self.disconnect()

        api.destroy_handle(
            self._handle
        )

        self._handle = None

    # Connection

    def connect(self):
        if self._connected:
            return

        self.open()

        try:
            api.connect(
                self.handle,
                self.ip_address,
                self.port,
            )

            self._connected = True

            # Always begin in a safe acquisition state

            api.disable_acquisition(
                self.handle
            )

            self.refresh_status()

        except Exception as exc:
            # A failed connect may have partially opened the native connection.
            try:
                api.disconnect(self.handle)
            except Exception as cleanup_error:
                # Retain the handle for recovery; close must retry disconnect.
                self._connected = True
                raise RuntimeError(f"Connection failed: {exc}; disconnect failed: {cleanup_error}") from exc
            self._connected = False
            raise

    def disconnect(self):
        if not self._connected:
            return

        # Always leave acquisition OFF

        api.disable_acquisition(
            self.handle
        )

        api.disconnect(
            self.handle
        )

        self._connected = False

        self._cycle_count = 0
        self._multichannel_supported = False
        self._multichannel_enabled = False

    # Status

    def refresh_status(self):
        self._require_connection()

        self._cycle_count = api.get_cycle_count(
            self.handle
        )

        state = api.get_multichannel_state(
            self.handle
        )

        self._multichannel_supported = (
            state["supported"]
        )

        self._multichannel_enabled = (
            state["enabled"]
        )

        return self.get_status()

    def get_status(self):
        return {
            "connected": self._connected,
            "ip_address": self.ip_address,
            "port": self.port,
            "cycle_count": self._cycle_count,
            "multichannel_supported": (
                self._multichannel_supported
            ),
            "multichannel_enabled": (
                self._multichannel_enabled
            ),
        }

    # Configuration

    def load_configuration(
        self,
        file_path,
        reconnect=True,
    ):
        self._require_connection()

        # Configuration must be written with acquisition OFF

        api.disable_acquisition(
            self.handle
        )

        api.load_configuration(
            self.handle,
            file_path,
        )

        if reconnect:
            self._reconnect_after_configuration()

        self.refresh_status()

        return self.get_status()

    def _reconnect_after_configuration(self):
        api.disable_acquisition(
            self.handle
        )

        api.disconnect(
            self.handle
        )

        self._connected = False

        try:
            api.connect(
                self.handle,
                self.ip_address,
                self.port,
            )

            self._connected = True

            api.disable_acquisition(
                self.handle
            )

        except Exception as exc:
            # Reconnect failures can also leave a partial native connection.
            try:
                api.disconnect(self.handle)
            except Exception as cleanup_error:
                self._connected = True
                raise RuntimeError(f"Reconnect failed: {exc}; disconnect failed: {cleanup_error}") from exc
            self._connected = False
            raise

    # Acquisition state

    def enable_acquisition(self):
        self._require_connection()

        api.enable_acquisition(
            self.handle
        )

    def disable_acquisition(self):
        if not self._connected:
            return

        api.disable_acquisition(
            self.handle
        )

    # Safety

    def _require_connection(self):
        if not self._connected:
            raise RuntimeError(
                "OEM-PA is not connected."
            )

    # Context manager

    def __enter__(self):
        self.connect()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()

        return False
