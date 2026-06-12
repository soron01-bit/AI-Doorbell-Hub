import os
import json

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')

DEFAULT_SETTINGS = {
    "camera_source": "0",  # "0" for webcam, or HTTP/RTSP URL for IP camera
    "recognition_threshold": 0.363,  # Cosine similarity threshold for SFace
    "bell_enabled": True,
    "cooldown_period": 10.0,  # seconds between bell sounds for the same person
    "camera_enabled": True,
    "video_rotation": 0,
    "detection_delay": 1.5
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            # Ensure all default keys exist
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception as e:
        print(f"Error loading settings: {e}")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False
