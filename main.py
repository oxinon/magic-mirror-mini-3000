"""
Einstiegspunkt.

Mit der Octal-SPIRAM-Firmware (GENERIC_S3_OCT_16M) stehen mehrere MB freier
Speicher zur Verfuegung -- Display, WLAN-Treiber und TLS-Verbindungen
koennen dauerhaft gleichzeitig aktiv bleiben. Der fruehere Workaround
(Display fuer jeden Netzwerk-Abruf kurz deinit/reinit) ist damit nicht
mehr noetig.
"""

import time
import gc
import uasyncio as asyncio
from machine import Pin

import config_store
import wifi_manager
import display as disp
import ntp_clock
import widgets
import webserver

WIDGET_ORDER = [
    "clock", "weather", "air_quality", "warnings", "calendar",
    "news", "crypto", "stocks", "ews", "defcon", "compliments",
]
WIDGET_LABELS = {
    "clock": "Clock", "weather": "Weather", "air_quality": "Air Quality",
    "warnings": "Warnings", "calendar": "Calendar", "news": "News",
    "crypto": "Crypto", "stocks": "Stocks", "ews": "Apocalypse EWS",
    "defcon": "DEFCON", "compliments": "Compliments",
}


def _active_widgets(cfg):
    """Nur die im Web-UI aktivierten Widgets, in der festen Grundreihenfolge.
    Faellt auf ["clock"] zurueck, falls versehentlich alles deaktiviert wurde
    -- sonst bliebe das Display leer."""
    w = cfg.get("widgets", {})
    active = [name for name in WIDGET_ORDER if w.get(name, {}).get("enabled", True)]
    return active or ["clock"]


_cache = {}
_cache_version = 0  # wird bei jedem erfolgreichen Refresh hochgezaehlt --
                     # display_task nutzt das, um auch bei stehendem Loop
                     # (manueller Modus) sofort neu zu zeichnen, sobald
                     # frische Daten da sind, statt erst beim naechsten
                     # Tastendruck oder Auto-Wechsel.

# T-Display S3: zwei eingebaute Tasten, GPIO0 (auch BOOT-Taste) und
# GPIO14, beide aktiv-low (gedrueckt = 0).
BTN_PREV = Pin(0, Pin.IN, Pin.PULL_UP)
BTN_NEXT = Pin(14, Pin.IN, Pin.PULL_UP)


def refresh_cache(cfg):
    global _cache_version
    print("Refreshing widget data...")
    try:
        _cache["weather"] = widgets.fetch_weather(cfg)
    except Exception as e:
        _cache["weather"] = {"ok": False, "msg": str(e)}
    gc.collect()
    try:
        _cache["air_quality"] = widgets.fetch_air_quality(cfg)
    except Exception as e:
        _cache["air_quality"] = {"ok": False, "msg": str(e)}
    gc.collect()
    try:
        _cache["warnings"] = widgets.fetch_warnings(cfg)
    except Exception as e:
        _cache["warnings"] = {"ok": False, "msg": str(e), "warnings": []}
    gc.collect()
    try:
        _cache["calendar"] = widgets.fetch_calendar(cfg)
    except Exception as e:
        _cache["calendar"] = {"ok": False, "msg": str(e), "events": []}
    gc.collect()
    try:
        _cache["news"] = widgets.fetch_news(cfg)
    except Exception as e:
        _cache["news"] = {"ok": False, "msg": str(e), "items": [], "source_name": ""}
    gc.collect()
    try:
        _cache["crypto"] = widgets.fetch_crypto(cfg)
    except Exception as e:
        _cache["crypto"] = {"ok": False, "msg": str(e), "prices": []}
    gc.collect()
    try:
        _cache["stocks"] = widgets.fetch_stocks(cfg)
    except Exception as e:
        _cache["stocks"] = {"ok": False, "msg": str(e), "quotes": []}
    gc.collect()
    try:
        _cache["ews"] = widgets.fetch_ews(cfg)
    except Exception as e:
        _cache["ews"] = {"ok": False, "msg": str(e)}
    gc.collect()
    try:
        _cache["defcon"] = widgets.fetch_defcon(cfg)
    except Exception as e:
        _cache["defcon"] = {"ok": False, "msg": str(e), "regions": []}
    gc.collect()
    _cache_version += 1


def draw_boot_screen(d, msg, sub=""):
    d.clear(disp.BLACK)
    d.text_centered("Magic Mirror Mini", disp.WIDTH // 2, 40, disp.ACCENT, "medium")
    d.text_centered("3000", disp.WIDTH // 2, 62, disp.ACCENT, "medium")
    d.text_centered(msg, disp.WIDTH // 2, 100, disp.FG, "small")
    if sub:
        d.text_centered(sub, disp.WIDTH // 2, 120, disp.FG_DIM, "small")
    d.show()


async def data_refresh_task(cfg):
    """Periodischer Hintergrund-Refresh. Wartet ZUERST das konfigurierte
    Intervall ab, bevor der erste Abruf laeuft -- main() hat direkt beim
    Start schon einen Refresh gemacht; ein sofortiger zweiter Durchlauf
    hier wuerde das Geraet (Display inklusive Uhr, Web-UI) fuer die ganze
    Dauer des zweiten, redundanten Abrufs erneut blockieren."""
    while True:
        minutes = cfg.get("general", {}).get("refresh_minutes", 10)
        await asyncio.sleep(max(60, minutes * 60))
        if wifi_manager.is_sta_connected():
            try:
                refresh_cache(cfg)
            except Exception as e:
                print("Error during data refresh:", e)


async def display_task(d, cfg):
    """Zeigt die Widgets im automatischen Wechsel. Sobald eine der beiden
    Tasten (GPIO0/GPIO14) gedrueckt wird, schaltet dauerhaft (bis zum
    naechsten Neustart) auf manuelles Durchblaettern um -- der
    Auto-Wechsel-Timer bleibt dann ausgesetzt, die Tasten blaettern
    vor/zurueck.

    Eine flache 100ms-Tick-Schleife (keine verschachtelten Blockier-
    Schleifen mehr) kuemmert sich um:
      - Tasten-Abfrage (immer reaktionsfaehig, auch waehrend die Uhr oder
        der News-Ticker laufen)
      - sekuendliches Neuzeichnen der Uhr
      - den News-Lauftext (Ticker-Scroll alle ~150ms)
      - sofortiges Neuzeichnen des aktuell gezeigten Widgets, sobald ein
        Hintergrund-Refresh neue Daten geliefert hat (_cache_version) --
        unabhaengig vom Auto-/Manual-Modus
      - den automatischen Widget-Wechsel, nur solange manuell noch nicht
        eingegriffen wurde
    Welche Widgets ueberhaupt in der Rotation auftauchen, wird bei jedem
    Zeichnen frisch aus der Konfiguration gelesen (Web-UI: Widgets
    einzeln ein-/ausschaltbar)."""
    idx = 0
    manual = False
    prev_prev_pressed = False
    prev_next_pressed = False
    active = [w for w in WIDGET_ORDER]  # wird beim ersten draw_current() sofort neu berechnet
    last_config_reload = 0  # erzwingt Reload beim allerersten Aufruf

    def draw_current():
        nonlocal active, last_config_reload
        # Config nicht bei JEDEM Zeichnen neu von Flash laden -- das waere
        # bei haeufigen Redraws (News-Ticker alle 150ms, Uhr jede Sekunde)
        # spuerbar langsam (Flash-I/O). Alle 2s reicht voellig, Aenderungen
        # uebers Web-UI sind selten und die kurze Verzoegerung unmerklich.
        now_ms = time.ticks_ms()
        if time.ticks_diff(now_ms, last_config_reload) >= 2000:
            fresh = config_store.load_config()
            cfg.clear()
            cfg.update(fresh)
            active = _active_widgets(cfg)
            last_config_reload = now_ms

        name = active[idx % len(active)]
        d.clear(disp.BLACK)
        if name == "clock":
            widgets.draw_clock(d, cfg)
        elif name == "weather":
            widgets.draw_weather(d, _cache.get("weather", {"ok": False, "msg": "Loading..."}))
        elif name == "air_quality":
            widgets.draw_air_quality(d, _cache.get("air_quality", {"ok": False, "msg": "Loading..."}))
        elif name == "warnings":
            widgets.draw_warnings(d, _cache.get("warnings", {"ok": False, "msg": "Loading...", "warnings": []}))
        elif name == "calendar":
            widgets.draw_calendar(d, _cache.get("calendar", {"ok": False, "msg": "Loading...", "events": []}))
        elif name == "news":
            widgets.draw_news(d, _cache.get("news", {"ok": False, "msg": "Loading...", "items": [], "source_name": ""}))
        elif name == "crypto":
            widgets.draw_crypto(d, _cache.get("crypto", {"ok": False, "msg": "Loading...", "prices": []}))
        elif name == "stocks":
            widgets.draw_stocks(d, _cache.get("stocks", {"ok": False, "msg": "Loading...", "quotes": []}))
        elif name == "ews":
            widgets.draw_ews(d, _cache.get("ews", {"ok": False, "msg": "Loading..."}))
        elif name == "defcon":
            widgets.draw_defcon(d, _cache.get("defcon", {"ok": False, "msg": "Loading...", "regions": []}))
        elif name == "compliments":
            widgets.draw_compliments(d, cfg)
        d.show()
        return name

    name = draw_current()
    last_switch = time.ticks_ms()
    last_second_tick = time.ticks_ms()
    last_ticker_tick = time.ticks_ms()
    last_seen_cache_version = _cache_version

    while True:
        await asyncio.sleep_ms(100)

        # -- Tasten abfragen (einfache Flankenerkennung, 100ms Poll-Intervall
        #    wirkt zugleich als Entprellung) --
        prev_pressed = BTN_PREV.value() == 0
        next_pressed = BTN_NEXT.value() == 0

        if prev_pressed and not prev_prev_pressed:
            manual = True
            idx = (idx - 1) % len(active)
            name = draw_current()
            last_switch = time.ticks_ms()
            last_second_tick = last_switch
            last_ticker_tick = last_switch

        if next_pressed and not prev_next_pressed:
            manual = True
            idx = (idx + 1) % len(active)
            name = draw_current()
            last_switch = time.ticks_ms()
            last_second_tick = last_switch
            last_ticker_tick = last_switch

        prev_prev_pressed = prev_pressed
        prev_next_pressed = next_pressed

        now = time.ticks_ms()

        # -- Frische Daten da? Aktuell gezeigtes Widget sofort neu zeichnen,
        #    egal ob Auto- oder manueller Modus (loest "Crypto bleibt stehen,
        #    obwohl schon neue Kurse da sind"). --
        if _cache_version != last_seen_cache_version:
            name = draw_current()
            last_seen_cache_version = _cache_version

        # -- Uhr: jede Sekunde neu zeichnen, egal ob Auto- oder manueller
        #    Modus (nur solange die Uhr das aktuell gezeigte Widget ist) --
        if name == "clock" and time.ticks_diff(now, last_second_tick) >= 1000:
            name = draw_current()
            last_second_tick = now

        # -- News-Ticker: Lauftext alle ~150ms weiterscrollen, solange News
        #    das aktuell gezeigte Widget ist --
        if name == "news" and time.ticks_diff(now, last_ticker_tick) >= 150:
            name = draw_current()
            last_ticker_tick = now

        # -- Automatischer Widget-Wechsel, nur solange noch keine Taste
        #    gedrueckt wurde --
        if not manual:
            cycle = max(3, cfg.get("general", {}).get("cycle_seconds", 8)) * 1000
            if time.ticks_diff(now, last_switch) >= cycle:
                idx = (idx + 1) % len(active)
                name = draw_current()
                last_switch = now
                last_second_tick = now
                last_ticker_tick = now


async def main():
    cfg = config_store.load_config()

    d = disp.Display()
    draw_boot_screen(d, "Starting...")

    mode, ip = wifi_manager.setup(cfg)

    # Webserver so frueh wie moeglich starten, damit das Web-UI schon
    # waehrend des (u.U. laengeren) ersten Datenabrufs erreichbar ist.
    asyncio.create_task(webserver.start())

    if mode == "sta":
        draw_boot_screen(d, "WiFi connected", ip)
        ntp_ok = ntp_clock.sync()
        draw_boot_screen(
            d, "Time synced" if ntp_ok else "NTP failed (continuing without)", ip
        )
        refresh_cache(cfg)
    else:
        ap_cfg = cfg.get("ap", {})
        draw_boot_screen(
            d,
            "Setup WiFi: " + ap_cfg.get("ssid", ""),
            "Browser: http://" + ip,
        )

    time.sleep(2)

    asyncio.create_task(data_refresh_task(cfg))
    await display_task(d, cfg)


try:
    asyncio.run(main())
except Exception as e:
    import sys
    print("=" * 40)
    print("main() aborted with an error:")
    sys.print_exception(e)
    print("=" * 40)
    print("No automatic reset, so the error stays visible here.")
    print("After debugging: import machine; machine.reset()")
