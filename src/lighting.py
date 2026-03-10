"""
LED Projector control with touch-based interaction model.

Touch model:
- 3 color touches: hold to light, release to blackout, combine to mix
- 6 animation touches: hold to animate with current/last color, release to stop
- Colors + animations can be combined
"""

import time
import threading
import math


class Projector:
    """Represents a single LED projector with DMX channel mapping."""

    def __init__(self, name, start_channel, channel_map, dmx_controller):
        self.name = name
        self.start_channel = start_channel
        self.channel_map = channel_map
        self.dmx = dmx_controller
        self._init_defaults()

    def _init_defaults(self):
        """Set sensible defaults for TOUR-mode channels."""
        # Linear dimmer for instant response
        if "dimmer_speed" in self.channel_map:
            self.dmx.set_channel(self._ch("dimmer_speed"), 10)
        # Disable color macro, auto, strobe by default
        for ch_name in ("color_macro", "auto", "auto_speed", "strobe"):
            if ch_name in self.channel_map:
                self.dmx.set_channel(self._ch(ch_name), 0)

    def _ch(self, name):
        return self.start_channel + self.channel_map.get(name, 0)

    @staticmethod
    def rgb_to_rgbw(r, g, b):
        """Convert RGB to RGBW using common-component subtraction."""
        w = min(r, g, b)
        return (r - w, g - w, b - w, w)

    def set_color(self, r, g, b, dimmer=255):
        self.dmx.set_channel(self._ch("dimmer"), dimmer)
        rr, gg, bb, ww = self.rgb_to_rgbw(r, g, b)
        self.dmx.set_channel(self._ch("red"), rr)
        self.dmx.set_channel(self._ch("green"), gg)
        self.dmx.set_channel(self._ch("blue"), bb)
        if "white" in self.channel_map:
            self.dmx.set_channel(self._ch("white"), ww)

    def set_dimmer(self, value):
        self.dmx.set_channel(self._ch("dimmer"), value)

    def set_strobe(self, value):
        """Set DMX strobe channel. TOUR mode: 0-10=off, 11-255=1-20Hz."""
        if "strobe" in self.channel_map:
            self.dmx.set_channel(self._ch("strobe"), value)

    def set_zoom(self, value):
        """Set zoom. 0-255 maps to 0-100%."""
        if "zoom" in self.channel_map:
            self.dmx.set_channel(self._ch("zoom"), value)

    def blackout(self):
        self.set_dimmer(0)
        self.set_strobe(0)

    def get_state(self):
        state = {}
        for name, offset in self.channel_map.items():
            ch = self.start_channel + offset
            state[name] = self.dmx.get_channel(ch)
        return state


class LightingEngine:
    """Touch-based lighting engine for 3 projectors."""

    def __init__(self, dmx_controller, settings):
        self.dmx = dmx_controller
        self.settings = settings
        self.projectors = []

        # Touch state
        self._active_colors = set()      # Set of color indices currently touched
        self._active_animation = None    # (type, speed_index) or None
        self._last_color = (0, 0, 0)     # Last mixed color (remembered for animation)

        # Effect thread
        self._effect_thread = None
        self._effect_running = False
        self._lock = threading.Lock()

    def add_projector(self, name, start_channel, channel_map):
        proj = Projector(name, start_channel, channel_map, self.dmx)
        self.projectors.append(proj)
        return proj

    # ---- Touch API ----

    def color_touch(self, color_index):
        """A color pad was touched (pressed)."""
        with self._lock:
            self._active_colors.add(color_index)
            mixed = self._mix_active_colors()
            self._last_color = mixed

        if self._active_animation:
            self._restart_animation()
        else:
            self._stop_effect()
            self._apply_fixed_color(mixed)

    def color_release(self, color_index):
        """A color pad was released."""
        with self._lock:
            self._active_colors.discard(color_index)
            has_colors = len(self._active_colors) > 0

        if has_colors:
            with self._lock:
                mixed = self._mix_active_colors()
                self._last_color = mixed
            if self._active_animation:
                self._restart_animation()
            else:
                self._apply_fixed_color(mixed)
        else:
            if not self._active_animation:
                self._blackout()
            # else: keep animation running with last color

    def animation_touch(self, anim_type, speed_index):
        """An animation pad was touched (pressed)."""
        with self._lock:
            self._active_animation = (anim_type, speed_index)
        self._restart_animation()

    def animation_release(self, anim_type, speed_index):
        """An animation pad was released."""
        with self._lock:
            if self._active_animation == (anim_type, speed_index):
                self._active_animation = None
            has_colors = len(self._active_colors) > 0

        self._stop_effect()
        if has_colors:
            mixed = self._mix_active_colors()
            self._apply_fixed_color(mixed)
        else:
            self._blackout()

    # ---- Color mixing ----

    def _mix_active_colors(self):
        """Additively mix all currently touched colors. Returns (r, g, b)."""
        r, g, b = 0, 0, 0
        for idx in self._active_colors:
            cr, cg, cb = self.settings.get_color(idx)
            r += cr
            g += cg
            b += cb
        return (min(255, r), min(255, g), min(255, b))

    def _apply_fixed_color(self, rgb):
        """Set all projectors to a fixed color."""
        r, g, b = rgb
        dimmer = self.settings.get("master_dimmer", 255)
        for proj in self.projectors:
            proj.set_strobe(0)
            proj.set_color(r, g, b, dimmer)

    def _blackout(self):
        """Blackout all projectors."""
        self._stop_effect()
        for proj in self.projectors:
            proj.blackout()

    # ---- Animations ----

    def _restart_animation(self):
        """Stop current effect and start the active animation."""
        self._stop_effect()
        # Clear DMX strobe channel (in case switching from strobe to chase)
        for proj in self.projectors:
            proj.set_strobe(0)
        with self._lock:
            anim = self._active_animation
        if not anim:
            return
        anim_type, speed_index = anim
        if anim_type == "strobe":
            self._apply_dmx_strobe(speed_index)
        elif anim_type == "chase":
            self._start_effect(self._chase_effect, speed_index)

    def _start_effect(self, effect_fn, speed_index):
        self._stop_effect()
        self._effect_running = True
        self._effect_thread = threading.Thread(
            target=effect_fn, args=(speed_index,), daemon=True
        )
        self._effect_thread.start()

    def _stop_effect(self):
        self._effect_running = False
        if self._effect_thread:
            self._effect_thread.join(timeout=1)
            self._effect_thread = None

    def _hz_to_strobe_dmx(self, hz):
        """Convert Hz (1-20) to DMX strobe value (11-255). TOUR: 0-10=off, 11-255=1-20Hz."""
        hz = max(1, min(20, hz))
        # Linear map: 1Hz->11, 20Hz->255
        return round(11 + (hz - 1) * (244 / 19))

    def _apply_dmx_strobe(self, speed_index):
        """Use the fixture's native DMX strobe channel."""
        r, g, b = self._last_color
        dimmer = self.settings.get("master_dimmer", 255)
        hz = self.settings.get_strobe_speed(speed_index)
        strobe_dmx = self._hz_to_strobe_dmx(hz)
        for proj in self.projectors:
            proj.set_color(r, g, b, dimmer)
            proj.set_strobe(strobe_dmx)

    def _chase_effect(self, speed_index):
        """Chase: projectors light up one at a time in sequence."""
        idx = 0
        while self._effect_running:
            hz = self.settings.get_chase_speed(speed_index)
            period = 1.0 / max(0.5, hz)
            r, g, b = self._last_color
            dimmer = self.settings.get("master_dimmer", 255)

            for i, proj in enumerate(self.projectors):
                if i == idx:
                    proj.set_color(r, g, b, dimmer)
                else:
                    proj.set_dimmer(0)

            idx = (idx + 1) % max(1, len(self.projectors))
            if not self._effect_running:
                break
            time.sleep(period)

    # ---- State ----

    def get_state(self):
        return {
            "master_dimmer": self.settings.get("master_dimmer", 255),
            "active_colors": list(self._active_colors),
            "active_animation": self._active_animation,
            "last_color": list(self._last_color),
            "projectors": [
                {"name": p.name, "state": p.get_state()}
                for p in self.projectors
            ],
        }

    def set_master_dimmer(self, value):
        value = max(0, min(255, int(value)))
        self.settings.set("master_dimmer", value)
        with self._lock:
            anim = self._active_animation
        if anim and anim[0] == "strobe":
            self._apply_dmx_strobe(anim[1])
        elif not anim and self._active_colors:
            mixed = self._mix_active_colors()
            self._apply_fixed_color(mixed)

    def update_strobe_if_active(self):
        """Re-apply DMX strobe if strobe animation is currently active."""
        with self._lock:
            anim = self._active_animation
        if anim and anim[0] == "strobe":
            self._apply_dmx_strobe(anim[1])

    def stop(self):
        """Clean shutdown."""
        self._stop_effect()
        self._blackout()
