"""
Persistent settings store.
Saves user-configurable values (colors, animation speeds) to a JSON file.
"""

import json
import os
import threading

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "settings.json")

DEFAULT_SETTINGS = {
    "colors": [
        {"r": 255, "g": 0,   "b": 0,   "label": "Color 1"},
        {"r": 0,   "g": 255, "b": 0,   "label": "Color 2"},
        {"r": 0,   "g": 0,   "b": 255, "label": "Color 3"},
        {"r": 255, "g": 255, "b": 255, "label": "Color 4"},
    ],
    "strobe_speeds": [
        {"hz": 2,  "label": "Strobe 1"},
        {"hz": 6,  "label": "Strobe 2"},
        {"hz": 15, "label": "Strobe 3"},
    ],
    "chase_speeds": [
        {"hz": 1,  "label": "Chase 1"},
        {"hz": 3,  "label": "Chase 2"},
        {"hz": 8,  "label": "Chase 3"},
    ],
    "master_dimmer": 255,
    "sample_map": {},  # key -> filename mapping for audio loops
}


class Settings:
    """Thread-safe persistent settings."""

    def __init__(self, path=SETTINGS_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        """Load settings from disk, merging with defaults."""
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    saved = json.load(f)
                # Merge: use saved values but keep defaults for missing keys
                extended = False
                for key in DEFAULT_SETTINGS:
                    if key in saved:
                        # Extend saved arrays with new default entries
                        if isinstance(saved[key], list) and isinstance(DEFAULT_SETTINGS[key], list):
                            if len(saved[key]) < len(DEFAULT_SETTINGS[key]):
                                saved[key].extend(DEFAULT_SETTINGS[key][len(saved[key]):])
                                extended = True
                        self._data[key] = saved[key]
                if extended:
                    self.save()
                print(f"[Settings] Loaded from {self._path}")
            except Exception as e:
                print(f"[Settings] Failed to load, using defaults: {e}")
        else:
            self.save()
            print(f"[Settings] Created default settings at {self._path}")

    def save(self):
        """Save current settings to disk."""
        with self._lock:
            try:
                with open(self._path, "w") as f:
                    json.dump(self._data, f, indent=2)
            except Exception as e:
                print(f"[Settings] Failed to save: {e}")

    def get_all(self):
        """Return a copy of all settings."""
        with self._lock:
            return dict(self._data)

    def get(self, key, default=None):
        """Get a setting value."""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        """Set a setting value and persist."""
        with self._lock:
            self._data[key] = value
        self.save()

    # --- Convenience accessors ---

    def get_color(self, index):
        """Get RGB tuple for a color index."""
        colors = self._data.get("colors", DEFAULT_SETTINGS["colors"])
        if 0 <= index < len(colors):
            c = colors[index]
            return (c["r"], c["g"], c["b"])
        return (0, 0, 0)

    def set_color(self, index, r, g, b):
        """Set a color and persist."""
        with self._lock:
            colors = self._data.get("colors", list(DEFAULT_SETTINGS["colors"]))
            if 0 <= index < len(colors):
                colors[index]["r"] = int(r)
                colors[index]["g"] = int(g)
                colors[index]["b"] = int(b)
                self._data["colors"] = colors
        self.save()

    def get_strobe_speed(self, index):
        """Get strobe speed in Hz for a speed index."""
        speeds = self._data.get("strobe_speeds", DEFAULT_SETTINGS["strobe_speeds"])
        if 0 <= index < len(speeds):
            return speeds[index]["hz"]
        return 5

    def set_strobe_speed(self, index, hz):
        """Set strobe speed and persist."""
        with self._lock:
            speeds = self._data.get("strobe_speeds", list(DEFAULT_SETTINGS["strobe_speeds"]))
            if 0 <= index < len(speeds):
                speeds[index]["hz"] = float(hz)
                self._data["strobe_speeds"] = speeds
        self.save()

    def get_chase_speed(self, index):
        """Get chase speed in Hz for a speed index."""
        speeds = self._data.get("chase_speeds", DEFAULT_SETTINGS["chase_speeds"])
        if 0 <= index < len(speeds):
            return speeds[index]["hz"]
        return 3

    def set_chase_speed(self, index, hz):
        """Set chase speed and persist."""
        with self._lock:
            speeds = self._data.get("chase_speeds", list(DEFAULT_SETTINGS["chase_speeds"]))
            if 0 <= index < len(speeds):
                speeds[index]["hz"] = float(hz)
                self._data["chase_speeds"] = speeds
        self.save()

    def get_sample(self, key):
        """Get the sample filename assigned to a key."""
        return self._data.get("sample_map", {}).get(key, "")

    def set_sample(self, key, filename):
        """Assign a sample file to a key and persist."""
        with self._lock:
            sm = self._data.get("sample_map", {})
            if filename:
                sm[key] = filename
            else:
                sm.pop(key, None)
            self._data["sample_map"] = sm
        self.save()
