"""WLAN-Verbindung: versucht zuerst als Client (STA) ins gespeicherte WLAN
zu kommen. Klappt das nicht (keine SSID hinterlegt oder Verbindung schlaegt
fehl), oeffnet das Geraet selbst einen Access Point, ueber den man das
Web-Setup erreichen kann -- genau das Verhalten, das du beschrieben hast.
"""

import network
import time


def connect_sta(ssid, password, timeout_s=15):
    if not ssid:
        return False

    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if not sta.isconnected():
        sta.connect(ssid, password)
        t0 = time.time()
        while not sta.isconnected():
            if time.time() - t0 > timeout_s:
                return False
            time.sleep(0.5)
    return sta.isconnected()


def start_ap(ssid, password):
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    if password and len(password) >= 8:
        ap.config(essid=ssid, password=password, authmode=network.AUTH_WPA_WPA2_PSK)
    else:
        ap.config(essid=ssid, authmode=network.AUTH_OPEN)
    return ap


def setup(cfg):
    """Gibt ein Tuple (mode, ip) zurueck. mode ist "sta" oder "ap"."""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)

    wifi_cfg = cfg.get("wifi", {})
    ok = connect_sta(wifi_cfg.get("ssid", ""), wifi_cfg.get("password", ""))

    if ok:
        ip = sta.ifconfig()[0]
        return "sta", ip

    # Kein WLAN konfiguriert oder Verbindung fehlgeschlagen -> eigenen AP
    # aufmachen, damit man ueber das Handy/Notebook das Setup erreichen kann.
    sta.active(False)
    ap_cfg = cfg.get("ap", {})
    ap = start_ap(ap_cfg.get("ssid", "MagicMirror-Setup"),
                   ap_cfg.get("password", "mirror1234"))
    t0 = time.time()
    while not ap.active() and time.time() - t0 < 5:
        time.sleep(0.2)
    ip = ap.ifconfig()[0]
    return "ap", ip


def is_sta_connected():
    return network.WLAN(network.STA_IF).isconnected()
