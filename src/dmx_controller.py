"""
DMX Controller for ENTTEC DMX USB MK2.
Handles serial communication using the ENTTEC Pro protocol.
"""

import serial
import threading
import time

# ENTTEC DMX USB Pro message labels
ENTTEC_PRO_START = 0x7E
ENTTEC_PRO_END = 0xE7
ENTTEC_PRO_SEND_DMX = 6  # Label for "Send DMX Packet"
ENTTEC_PRO_GET_WIDGET_INFO = 3

DMX_UNIVERSE_SIZE = 512


class DMXController:
    """Controls DMX output via ENTTEC DMX USB MK2."""

    def __init__(self, port="/dev/ttyUSB0", baudrate=57600):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.universe = bytearray(DMX_UNIVERSE_SIZE + 1)  # +1 for start code (0x00)
        self.universe[0] = 0  # DMX start code
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._refresh_rate = 40  # ~25 fps

    def connect(self):
        """Open serial connection to the ENTTEC interface."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_TWO,
                parity=serial.PARITY_NONE,
            )
            time.sleep(0.5)  # Let the interface settle
            print(f"[DMX] Connected to {self.port}")
            return True
        except serial.SerialException as e:
            print(f"[DMX] Connection failed: {e}")
            return False

    def disconnect(self):
        """Close the serial connection."""
        self.stop_sending()
        if self.serial and self.serial.is_open:
            self.serial.close()
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
            return
        with self._lock:
            msg = self._build_message(ENTTEC_PRO_SEND_DMX, self.universe)
        try:
            self.serial.write(msg)
        except serial.SerialException as e:
            print(f"[DMX] Send error: {e}")

    def _send_loop(self):
        """Continuously send DMX frames at the configured refresh rate."""
        while self._running:
            self._send_dmx_frame()
            time.sleep(1.0 / self._refresh_rate)

    def start_sending(self):
        """Start the DMX send loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()
        print("[DMX] Sending started")

    def stop_sending(self):
        """Stop the DMX send loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        print("[DMX] Sending stopped")

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
        return self.serial is not None and self.serial.is_open


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
