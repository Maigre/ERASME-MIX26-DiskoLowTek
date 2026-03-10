"""
Makey Makey Input Handler — Touch model.
Maps key press/release events to color and animation touch/release actions.
"""

import threading


class MakeyMakeyHandler:
    """Listens for Makey Makey key events with press/release tracking."""

    MAKEY_VENDOR_ID = 0x2A66

    def __init__(self, touch_mapping, on_color_touch=None, on_color_release=None,
                 on_animation_touch=None, on_animation_release=None,
                 key_state_callback=None):
        """
        Args:
            touch_mapping: dict with "colors" and "animations" key mappings
            on_color_touch: fn(color_index)
            on_color_release: fn(color_index)
            on_animation_touch: fn(anim_type, speed_index)
            on_animation_release: fn(anim_type, speed_index)
            key_state_callback: fn(key, pressed) for UI updates
        """
        self.touch_mapping = touch_mapping
        self.on_color_touch = on_color_touch
        self.on_color_release = on_color_release
        self.on_animation_touch = on_animation_touch
        self.on_animation_release = on_animation_release
        self.key_state_callback = key_state_callback

        self._running = False
        self._thread = None
        self._device = None
        self._evdev_available = False
        self._key_states = {}

        # Build reverse lookup: key_name -> {"type": "color"/"animation", ...}
        self._key_actions = {}
        for key, cfg in touch_mapping.get("colors", {}).items():
            self._key_actions[key] = {"type": "color", "index": cfg["index"]}
        for key, cfg in touch_mapping.get("animations", {}).items():
            self._key_actions[key] = {
                "type": "animation",
                "anim_type": cfg["type"],
                "speed_index": cfg["speed_index"],
            }

        try:
            import evdev  # noqa: F401
            self._evdev_available = True
        except ImportError:
            print("[MakeyMakey] evdev not available — web-only mode")

    def find_makey_makey(self):
        if not self._evdev_available:
            return None
        import evdev
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            name_lower = device.name.lower()
            if ("makey" in name_lower
                    or "joylabz" in name_lower
                    or "arduino leonardo" in name_lower
                    or device.info.vendor == self.MAKEY_VENDOR_ID):
                if "keyboard" in name_lower or not any(
                    "keyboard" in d.name.lower()
                    for d in devices
                    if d.info.vendor == device.info.vendor and d.path != device.path
                ):
                    print(f"[MakeyMakey] Found: {device.name} at {device.path}")
                    return device
        print("[MakeyMakey] No Makey Makey found. Available devices:")
        for device in devices:
            print(f"  - {device.name} ({device.path}) vendor={hex(device.info.vendor)}")
        return None

    def start(self):
        if not self._evdev_available:
            print("[MakeyMakey] Running in web-only mode (no evdev)")
            return False
        self._device = self.find_makey_makey()
        if not self._device:
            print("[MakeyMakey] No device found — web-only mode")
            return False
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        print("[MakeyMakey] Listening for input")
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self._device:
            self._device.close()
            self._device = None
        print("[MakeyMakey] Stopped")

    def _read_loop(self):
        import evdev
        from evdev import ecodes
        try:
            for event in self._device.read_loop():
                if not self._running:
                    break
                if event.type == ecodes.EV_KEY:
                    key_name = ecodes.KEY.get(event.code, f"KEY_{event.code}")
                    if isinstance(key_name, list):
                        key_name = key_name[0]
                    short = key_name.replace("KEY_", "").lower()

                    if event.value == 1:  # press
                        self._handle_touch(short, pressed=True)
                    elif event.value == 0:  # release
                        self._handle_touch(short, pressed=False)
        except Exception as e:
            print(f"[MakeyMakey] Read error: {e}")
            self._running = False

    def _handle_touch(self, key, pressed):
        """Route a key press/release to the appropriate callback."""
        self._key_states[key] = pressed
        if self.key_state_callback:
            self.key_state_callback(key, pressed)

        action = self._key_actions.get(key)
        if not action:
            return

        if action["type"] == "color":
            idx = action["index"]
            if pressed:
                print(f"[MakeyMakey] Color {idx} touch")
                if self.on_color_touch:
                    self.on_color_touch(idx)
            else:
                print(f"[MakeyMakey] Color {idx} release")
                if self.on_color_release:
                    self.on_color_release(idx)

        elif action["type"] == "animation":
            atype = action["anim_type"]
            sidx = action["speed_index"]
            if pressed:
                print(f"[MakeyMakey] Animation {atype}[{sidx}] touch")
                if self.on_animation_touch:
                    self.on_animation_touch(atype, sidx)
            else:
                print(f"[MakeyMakey] Animation {atype}[{sidx}] release")
                if self.on_animation_release:
                    self.on_animation_release(atype, sidx)

    def handle_web_touch(self, key, pressed):
        """Handle a key event from the web UI."""
        self._handle_touch(key.lower(), pressed)

    def get_key_states(self):
        """Return current pressed state of all mapped keys."""
        states = {}
        for key in self._key_actions:
            states[key] = self._key_states.get(key, False)
        return states

    def get_all_keys_info(self):
        """Return key info including labels for the UI."""
        result = {}
        for key, cfg in self.touch_mapping.get("colors", {}).items():
            result[key] = {
                "type": "color",
                "index": cfg["index"],
                "label": cfg.get("label", f"Color {cfg['index']+1}"),
            }
        for key, cfg in self.touch_mapping.get("animations", {}).items():
            result[key] = {
                "type": "animation",
                "anim_type": cfg["type"],
                "speed_index": cfg["speed_index"],
                "label": cfg.get("label", f"{cfg['type']} {cfg['speed_index']+1}"),
            }
        return result

    @property
    def is_running(self):
        return self._running
