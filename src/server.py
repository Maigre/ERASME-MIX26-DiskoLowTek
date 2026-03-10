"""
MIX LowTech26 — DMX Controller Server
Flask + Socket.IO server with touch-based interaction model.
"""

import json
import os
import argparse
import glob

from flask import Flask, send_from_directory, jsonify
from flask_socketio import SocketIO

from dmx_controller import DMXController, DummyDMXController
from lighting import LightingEngine
from makey_handler import MakeyMakeyHandler
from settings import Settings

# ---- Load Config ----

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


# ---- App Setup ----

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = "mix-lowtech26"
socketio = SocketIO(app, cors_allowed_origins="*")


def create_app(use_dummy=False):
    config = load_config()
    settings = Settings()

    # DMX
    if use_dummy:
        dmx = DummyDMXController()
    else:
        dmx_cfg = config.get("dmx", {})
        dmx = DMXController(
            port=dmx_cfg.get("port", "/dev/ttyUSB0"),
            baudrate=dmx_cfg.get("baudrate", 57600),
        )
    dmx.connect()
    dmx.start_sending()

    # Lighting Engine
    engine = LightingEngine(dmx, settings)
    for proj_cfg in config.get("projectors", []):
        engine.add_projector(
            name=proj_cfg["name"],
            start_channel=proj_cfg["start_channel"],
            channel_map=proj_cfg["channels"],
        )

    # Makey Makey
    touch_mapping = config.get("touch_mapping", {})

    def on_key_state(key, pressed):
        socketio.emit("key_state", {"key": key, "pressed": pressed})
        socketio.emit("state_update", engine.get_state())

    makey = MakeyMakeyHandler(
        touch_mapping=touch_mapping,
        on_color_touch=engine.color_touch,
        on_color_release=engine.color_release,
        on_animation_touch=engine.animation_touch,
        on_animation_release=engine.animation_release,
        key_state_callback=on_key_state,
    )
    makey_connected = makey.start()

    return dmx, engine, makey, makey_connected, config, settings


# ---- Globals ----
dmx = None
engine = None
makey = None
makey_connected = False
config = None
settings = None


# ---- Routes ----

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/samples")
def list_samples():
    """Return list of audio files in samples/ directory."""
    exts = (".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a")
    files = []
    if os.path.isdir(SAMPLES_DIR):
        for f in sorted(os.listdir(SAMPLES_DIR)):
            if f.lower().endswith(exts):
                files.append(f)
    return jsonify(files)


@app.route("/samples/<path:filename>")
def serve_sample(filename):
    """Serve an audio file from samples/ directory."""
    return send_from_directory(SAMPLES_DIR, filename)


# ---- Socket.IO Events ----

@socketio.on("connect")
def on_connect():
    socketio.emit("status", {
        "dmx_connected": dmx.is_connected,
        "dmx_dummy": isinstance(dmx, DummyDMXController),
        "makey_connected": makey_connected,
    })
    socketio.emit("state_update", engine.get_state())
    socketio.emit("key_states", makey.get_key_states())
    socketio.emit("keys_info", makey.get_all_keys_info())
    socketio.emit("settings_update", settings.get_all())


@socketio.on("get_state")
def on_get_state():
    socketio.emit("state_update", engine.get_state())


@socketio.on("key_press")
def on_key_press(data):
    key = data.get("key", "")
    makey.handle_web_touch(key, pressed=True)
    socketio.emit("state_update", engine.get_state())


@socketio.on("key_release")
def on_key_release(data):
    key = data.get("key", "")
    makey.handle_web_touch(key, pressed=False)
    socketio.emit("state_update", engine.get_state())


@socketio.on("set_master_dimmer")
def on_set_master_dimmer(data):
    value = data.get("value", 255)
    engine.set_master_dimmer(value)
    socketio.emit("state_update", engine.get_state())
    socketio.emit("settings_update", settings.get_all())


@socketio.on("set_color")
def on_set_color(data):
    index = data.get("index", 0)
    r = data.get("r", 0)
    g = data.get("g", 0)
    b = data.get("b", 0)
    settings.set_color(index, r, g, b)
    socketio.emit("settings_update", settings.get_all())


@socketio.on("set_strobe_speed")
def on_set_strobe_speed(data):
    index = data.get("index", 0)
    hz = data.get("hz", 5)
    settings.set_strobe_speed(index, hz)
    engine.update_strobe_if_active()
    socketio.emit("settings_update", settings.get_all())


@socketio.on("set_chase_speed")
def on_set_chase_speed(data):
    index = data.get("index", 0)
    hz = data.get("hz", 3)
    settings.set_chase_speed(index, hz)
    socketio.emit("settings_update", settings.get_all())


@socketio.on("get_settings")
def on_get_settings():
    socketio.emit("settings_update", settings.get_all())


@socketio.on("set_sample")
def on_set_sample(data):
    key = data.get("key", "")
    sample = data.get("sample", "")  # empty string = none
    settings.set_sample(key, sample)
    socketio.emit("settings_update", settings.get_all())


# ---- Main ----

def main():
    global dmx, engine, makey, makey_connected, config, settings

    parser = argparse.ArgumentParser(description="MIX LowTech26 DMX Controller")
    parser.add_argument("--dummy", action="store_true", help="Use dummy DMX (no hardware)")
    parser.add_argument("--port", type=int, default=None, help="Web server port")
    parser.add_argument("--host", type=str, default=None, help="Web server host")
    args = parser.parse_args()

    dmx, engine, makey, makey_connected, config, settings = create_app(use_dummy=args.dummy)

    srv_cfg = config.get("server", {})
    host = args.host or srv_cfg.get("host", "0.0.0.0")
    port = args.port or srv_cfg.get("port", 5000)

    print(f"\n{'='*50}")
    print(f"  MIX LowTech26 — DMX Controller")
    print(f"  Web UI: http://{host}:{port}")
    print(f"  DMX: {'Dummy' if isinstance(dmx, DummyDMXController) else dmx.port}")
    print(f"  Makey: {'Connected' if makey_connected else 'Web-only'}")
    print(f"{'='*50}\n")

    try:
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nShutting down...")
        engine.stop()
        makey.stop()
        dmx.disconnect()


if __name__ == "__main__":
    main()
