"""Laedt/speichert die Geraete-Konfiguration als JSON in /config.json.

Struktur bewusst analog zum Docker-Magic-Mirror-Projekt gehalten (siehe
README des Hauptprojekts): pro Widget ein eigener Unter-Key.
"""

import json

CONFIG_PATH = "/config.json"

DEFAULT_CONFIG = {
    "wifi": {
        "ssid": "",
        "password": "",
    },
    "ap": {
        "ssid": "MagicMirror-Setup",
        "password": "mirror1234",
    },
    "general": {
        "cycle_seconds": 8,       # Sekunden pro Widget im Wechsel
        "refresh_minutes": 10,    # wie oft Daten neu geholt werden
        "utc_offset": 1,          # Standardzeit-Offset (Deutschland: 1 = CET)
        "dst_auto": True,         # Sommerzeit automatisch (EU-Regel)
        "hour24": True,
        "show_seconds": True,
        "brightness": 100,        # nur informativ, Backlight ist an/aus
    },
    "widgets": {
        "clock": {
            "enabled": True,
        },
        "weather": {
            "enabled": True,
            "location": "Hamburg",
            "latitude": 53.5511,
            "longitude": 9.9937,
            "units": "celsius",
            "wind_warn_kmh": 60,
            "heat_warn_c": 32,
            "cold_warn_c": -10,
        },
        "air_quality": {
            "enabled": True,
            "location": "Hamburg",
            "latitude": 53.5511,
            "longitude": 9.9937,
        },
        "warnings": {
            "enabled": True,
            "location": "",
            "ars": "",
        },
        "calendar": {
            "enabled": True,
            "icalUrl": "",
            "maxEvents": 5,
            "daysAhead": 14,
        },
        "news": {
            "enabled": True,
            # Bis zu 3 Quellen, wird bei jedem Refresh reihum gewechselt
            # -- Standardwerte 1:1 aus der README des Docker-Projekts.
            "sources": [
                {"name": "Tagesschau", "feedUrl": "https://www.tagesschau.de/xml/rss2/"},
                {"name": "Spiegel", "feedUrl": "https://www.spiegel.de/schlagzeilen/index.rss"},
                {"name": "Heise", "feedUrl": "https://www.heise.de/rss/heise-atom.xml"},
            ],
            "max_items": 5,
        },
        "crypto": {
            "enabled": True,
            "symbols": ["bitcoin", "ethereum"],
            "currency": "usd",
        },
        "stocks": {
            "enabled": True,
            "symbols": ["AAPL", "SAP.DE"],
        },
        "ews": {
            "enabled": True,
        },
        "defcon": {
            "enabled": True,
            "url": "",
            "api_key": "",
        },
        "compliments": {
            "enabled": True,
            "messages": [
                "You look great today!",
                "Your smile lights up the room!",
                "You're doing an amazing job!",
                "Today is going to be a good day!",
                "You've got this!",
                "Someone out there thinks you're awesome!",
            ],
        },
    },
}


def _deep_merge(base, override):
    """override in base einmischen, fehlende Keys aus base behalten
    (schuetzt vor kaputter Konfiguration nach Firmware-/Feature-Updates)."""
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy ohne Modul-Import
    try:
        with open(CONFIG_PATH) as f:
            saved = json.load(f)
        _deep_merge(cfg, saved)
    except (OSError, ValueError):
        pass  # noch keine Konfiguration vorhanden -> Defaults nutzen
    return cfg


def save_config(cfg):
    tmp_path = CONFIG_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(cfg, f)
    try:
        import os
        os.remove(CONFIG_PATH)
    except OSError:
        pass
    import os
    os.rename(tmp_path, CONFIG_PATH)
