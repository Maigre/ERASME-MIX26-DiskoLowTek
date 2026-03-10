"""
DMX Controller for ENTTEC DMX USB MK2.
Handles serial communication using the ENTTEC Pro protocol.
Supports hot-plug: automatic reconnection on device unplug/replug.
"""

import serial
import serial.tools.list_ports
import threading
import time
import os

# ENTTEC DMX USB Pro message labels
ENTTEC_PRO_START = 0x7E
ENTTEC_PRO_END = 0xE7
ENTTEC_PRO_SEND_DMX = 6  # Label for "Send DMX Packet"
ENTTEC_PRO_GET_WIDGET_INFO = 3

DMX_UNIVERSE_SIZE = 512

# ENTTEC vendor/product IDs
ENTTEC_VENDOR_ID = 0x0403
ENTTEC_PRODUCT_IDS = {0x6001, 0x6010, 0x6014}

RECONNECT_INTERVAL = 2  # seconds between reconnect attempts


class DMXController:
    """Controls DMX output via ENTTEC DMX USB MK2 with hot-plug support."""

    def __init__(self, port="/dev/ttyUSB0", baudrate=57600, on_status_change=None):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.universe = bytearray(DMX_UNIVERSE_SIZE + 1)  # +1 for start code (0x00)
        self.universe[0] = 0  # DMX start code
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._refresh_rate = 40  # ~25 fps
        self._connected = False
        self._consecutive_errors = 0
        self._max_errors = 3
        self.on_status_change = on_status_change  # callback(connected: bool)

    def _find_enttec_port(self):
        """Auto-detect ENTTEC DMX USB device port."""
        # First try the configured port
        if os.path.exists(self.port):
            return self.port
        # Scan for ENTTEC devices
        for p in serial.tools.list_ports.comports():
            if p.vid == ENTTEC_VENDOR_ID and p.pid in ENTTEC_PRODUCT_IDS:
                print(f"[DMX] Auto-detected ENTTEC at {p.device}")
                return p.device
            if p.description and "dmx" in p.description.lower():
                return p.device
        return None

    def connect(self):
        """Open serial connection to the ENTTEC interface."""
        port = self._find_enttec_port()
        if not port:
            print(f"[DMX] No ENTTEC device found (configured: {self.port})")
            self._set_connected(False)
            return False
        try:
            self.serial = serial.Serial(
                port=port,
                baudrate=self.baudrate,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_TWO,
                parity=serial.PARITY_NONE,
            )
            time.sleep(0.5)  # Let the interface settle
            self._consecutive_errors = 0
            self._set_connected(True)
            print(f"[DMX] Connected to {port}")
            return True
        except (serial.SerialException, OSError) as e:
            print(f"[DMX] Connection failed: {e}")
            self._set_connected(False)
            return False

    def _set_connected(self, connected):
        """Update connection state and fire callback on change."""
        if connected != self._connected:
            self._connected = connected
            if self.on_status_change:
                try:
                    self.on_status_change(connected)
                except Exception:
                    pass

    def _try_reconnect(self):
        """Attempt to reconnect to the device."""
        # Close stale handle
        try:
            if self.serial:
                self.serial.close()
        except Exception:
            pass
        self.serial = None
        return self.connect()

    def disconnect(self):
        """Close the serial connection."""
        self.stop_sending()
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
        except Exception:
            pass
        self.serial = None
        self._set_connected(False)
        print("[DMX] Disconnected")

    def _build_message(self, label, data):
        """Build an ENTTEC Pro protocol message."""
        data_len = len(data)
        msg = bytearray()
        msg.append(ENTTEC_PRO_START)
        msg.append(label)
        msg.append(data_len & 0xFF)         # Length LSB
        msg.append((data_len >> 8) & 0xFF)  # Length MSB
        msg.extend(data)
        msg.append(ENTTEC_PRO_END)
        return msg

    def _send_dmx_frame(self):
        """Send a single DMX frame to the interface."""
        if not self.serial or not self.serial.is_open:
            return False
        with self._lock:
            msg = self._build_message(ENTTEC_PRO_SEND_DMX, self.universe)
        try:
            self.serial.write(msg)
            self._consecutive_errors = 0
            return True
        except (serial.SerialException, OSError) as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._max_errors:
                print(f"[DMX] Device lost: {e}")
                self._set_connected(False)
                try:
                    self.serial.close()
                except Exception:
                    pass
                self.serial = None
            return False

    def _send_loop(self):
        """Continuously send DMX frames; reconnect on device loss."""
        while self._running:
            if self._connected and self.serial:
                self._send_dmx_frame()
                time.sleep(1.0 / self._refresh_rate)
            else:
                # Not connected — try to reconnect
                if self._try_reconnect():
                    print("[DMX] Reconnected — resuming output")
                else:
                    time.sleep(RECONNECT_INTERVAL)

    def start_sending(self):
        """Start the DMX send loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()
        print("[DMX] Send loop started")

    def stop_sending(self):
        """Stop the DMX send loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        print("[DMX] Send loop stopped")

    def set_channel(self, channel, value):
        """Set a single DMX channel value (1-indexed, 1-512)."""
        if 1 <= channel <= DMX_UNIVERSE_SIZE:
            with self._lock:
                self.universe[channel] = max(0, min(255, int(value)))

    def get_channel(self, channel):
        """Get a single DMX channel value (1-indexed)."""
        if 1 <= channel <= DMX_UNIVERSE_SIZE:
            return self.universe[channel]
        return 0

    def set_channels(self, start_channel, values):
        """Set multiple consecutive channels starting from start_channel (1-indexed)."""
        with self._lock:
            for i, val in enumerate(values):
                ch = start_channel + i
                if 1 <= ch <= DMX_UNIVERSE_SIZE:
                    self.universe[ch] = max(0, min(255, int(val)))

    def blackout(self):
        """Set all channels to 0."""
        with self._lock:
            for i in range(1, DMX_UNIVERSE_SIZE + 1):
                self.universe[i] = 0
        print("[DMX] Blackout")

    def get_universe_snapshot(self):
        """Return a copy of the current universe state (channels 1-512)."""
        with self._lock:
            return list(self.universe[1:])

    @property
    def is_connected(self):
        return self._connected


class DummyDMXController:
    """Fake DMX controller for testing without hardware."""

    def __init__(self, port="dummy", baudrate=57600):
        self.port = port
        self.universe = bytearray(DMX_UNIVERSE_SIZE + 1)
        self._running = False
        self._lock = threading.Lock()

    def connect(self):
        print("[DMX-Dummy] Simulated connection")
        return True

    def disconnect(self):
        self._running = False
        print("[DMX-Dummy] Disconnected")

    def start_sending(self):
        self._running = True
        print("[DMX-Dummy] Sending started (simulated)")

    def stop_sending(self):
        self._running = False
        print("[DMX-Dummy] Sending stopped")

    def set_channel(self, channel, value):
        if 1 <= channel <= DMX_UNIVERSE_SIZE:
            with self._lock:
                self.universe[channel] = max(0, min(255, int(value)))

    def get_channel(self, channel):
        if 1 <= channel <= DMX_UNIVERSE_SIZE:
            return self.universe[channel]
        return 0

    def set_channels(self, start_channel, values):
        with self._lock:
            for i, val in enumerate(values):
                ch = start_channel + i
                if 1 <= ch <= DMX_UNIVERSE_SIZE:
                    self.universe[ch] = max(0, min(255, int(val)))

    def blackout(self):
        with self._lock:
            for i in range(1, DMX_UNIVERSE_SIZE + 1):
                self.universe[i] = 0
        print("[DMX-Dummy] Blackout")

    def get_universe_snapshot(self):
        with self._lock:
            return list(self.universe[1:])

    @property
    def is_connected(self):
        return True
