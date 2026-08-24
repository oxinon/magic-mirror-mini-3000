"""The widgets: weather, air quality, official warnings (NINA), NTP clock,
news (RSS), crypto, stocks, Apocalypse EWS, DEFCON and compliments. Data
sources match the Docker Magic Mirror project 1:1 -- no API key needed
anywhere:
  - Weather/air quality: Open-Meteo
  - Warnings: warnung.bund.de (NINA / BBK)
  - News: RSS/Atom feeds (own lightweight parser, no feedparser on device)
  - Crypto: CoinGecko
  - Stocks: Yahoo Finance chart endpoint
  - EWS: ews.kylemcdonald.net public snapshot feed
  - DEFCON: user's own JSON endpoint (e.g. ai-defcon.com/defcon-assistant)
  - Compliments: purely local, no network needed
"""

import time
import random
import urequests
import ntp_clock
import display as disp
import romans as CLOCK_FONT

WEATHER_CODES = {
    0: ("Clear sky", "clear"), 1: ("Mostly clear", "clear"),
    2: ("Partly cloudy", "cloudy"), 3: ("Overcast", "cloudy"),
    45: ("Fog", "fog"), 48: ("Rime fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Dense drizzle", "rain"),
    56: ("Freezing drizzle", "rain"), 57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Rain showers", "rain"), 81: ("Rain showers", "rain"), 82: ("Violent showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm/hail", "storm"), 99: ("Severe storm", "storm"),
}

EWS_DASHBOARD_URL = "https://pub-49bb6a6f314c47be9b481c25e5f6ca9e.r2.dev/dashboard.json"

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "GBp": "\u00a3", "CHF": "CHF",
    "JPY": "\u00a5", "CAD": "C$", "AUD": "A$", "HKD": "HK$",
}

def _get_json(url, timeout=10):
    r = urequests.get(url, timeout=timeout)
    try:
        return r.json()
    finally:
        r.close()


# ---------------------------------------------------------------------
# Fetch functions: return a dict with "ok" + data, or an error message
# ---------------------------------------------------------------------

def fetch_weather(cfg):
    w = cfg["widgets"]["weather"]
    lat, lon = w.get("latitude"), w.get("longitude")
    if lat is None or lon is None:
        return {"ok": False, "msg": "No location configured"}
    units = w.get("units", "celsius")
    temp_unit = "fahrenheit" if units == "fahrenheit" else "celsius"
    url = (
        "https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "wind_speed_10m,wind_gusts_10m,weather_code"
        "&temperature_unit={}&wind_speed_unit=kmh&timezone=auto"
    ).format(lat, lon, temp_unit)
    try:
        data = _get_json(url)
        cur = data.get("current", {})
        code = cur.get("weather_code", 0)
        desc, group = WEATHER_CODES.get(int(code), ("Unknown", "cloudy"))

        temp = cur.get("temperature_2m")
        gusts = cur.get("wind_gusts_10m")
        warn = None
        if gusts is not None and gusts >= w.get("wind_warn_kmh", 60):
            warn = "Strong gusts {} km/h".format(round(gusts))
        elif units != "fahrenheit" and temp is not None and temp >= w.get("heat_warn_c", 32):
            warn = "Heat {} C".format(round(temp))
        elif units != "fahrenheit" and temp is not None and temp <= w.get("cold_warn_c", -10):
            warn = "Cold {} C".format(round(temp))
        elif group == "storm":
            warn = "Thunderstorm"

        return {
            "ok": True,
            "location": w.get("location", ""),
            "group": group,
            "description": desc,
            "temperature": temp,
            "feels_like": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "gusts": gusts,
            "unit": "F" if units == "fahrenheit" else "C",
            "warning": warn,
        }
    except Exception as e:
        return {"ok": False, "msg": "Weather error: {}".format(e)}


def fetch_air_quality(cfg):
    a = cfg["widgets"]["air_quality"]
    lat, lon = a.get("latitude"), a.get("longitude")
    if lat is None or lon is None:
        return {"ok": False, "msg": "No location configured"}
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={}"
        "&longitude={}&current=european_aqi,pm10,pm2_5,ozone&timezone=auto"
    ).format(lat, lon)
    try:
        data = _get_json(url)
        cur = data.get("current", {})
        return {
            "ok": True,
            "location": a.get("location", ""),
            "aqi": cur.get("european_aqi"),
            "pm10": cur.get("pm10"),
            "pm25": cur.get("pm2_5"),
            "ozone": cur.get("ozone"),
        }
    except Exception as e:
        return {"ok": False, "msg": "Air quality error: {}".format(e)}


def fetch_warnings(cfg):
    w = cfg["widgets"]["warnings"]
    ars = (w.get("ars") or "").strip()
    if not ars:
        return {"ok": False, "msg": "No location configured", "warnings": [], "location": ""}
    url = "https://warnung.bund.de/api31/dashboard/{}.json".format(ars)
    try:
        data = _get_json(url)
        warnings = []
        for item in data if isinstance(data, list) else []:
            payload = item.get("payload", {}) or {}
            pdata = payload.get("data", {}) or {}
            title = pdata.get("headline") or "Warning"
            sev_raw = pdata.get("severity", "")
            sev = 7 if sev_raw in ("Severe", "Extreme") else 6
            warnings.append({"title": title, "severity": sev})
        return {"ok": True, "warnings": warnings, "location": w.get("location", "")}
    except Exception as e:
        return {"ok": False, "msg": "Warnings error: {}".format(e), "warnings": [], "location": w.get("location", "")}


def geocode_search(query):
    """Location search for weather/air quality (Open-Meteo geocoding)."""
    url = "https://geocoding-api.open-meteo.com/v1/search?name={}&count=5&language=en&format=json".format(query)
    data = _get_json(url)
    results = []
    for res in data.get("results", []) or []:
        parts = [res.get("name")]
        if res.get("admin1"):
            parts.append(res["admin1"])
        if res.get("country"):
            parts.append(res["country"])
        results.append({
            "label": ", ".join(p for p in parts if p),
            "latitude": res.get("latitude"),
            "longitude": res.get("longitude"),
        })
    return results


def ags_search(query):
    """Location search for NINA warnings (German official region code).
    Note: city-states like Hamburg/Berlin/Bremen have no separate
    "district" entry in the API response (no Kreis-level above the city
    itself) -- fall back to the municipality key in that case."""
    is_plz = query.isdigit() and len(query) == 5
    param = "postalCode" if is_plz else "name"
    url = "https://openplzapi.org/de/Localities?{}={}".format(param, query)
    data = _get_json(url)
    results = []
    seen = set()
    for loc in data if isinstance(data, list) else []:
        district = loc.get("district") or {}
        municipality = loc.get("municipality") or {}
        federal_state = loc.get("federalState") or {}
        key_source = district.get("key") or municipality.get("key")
        if not key_source:
            continue
        ars = key_source + "0" * (12 - len(key_source))
        if ars in seen:
            continue
        seen.add(ars)
        area_name = district.get("name") or municipality.get("name")
        parts = [loc.get("name"), area_name, federal_state.get("name")]
        results.append({"label": ", ".join(p for p in parts if p), "ars": ars})
        if len(results) >= 8:
            break
    return results


def fetch_crypto(cfg):
    c = cfg["widgets"]["crypto"]
    symbols = c.get("symbols") or []
    currency = (c.get("currency") or "usd").lower()
    if not symbols:
        return {"ok": False, "msg": "No coins configured", "prices": []}

    ids = ",".join(symbols)
    url = "https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies={}&include_24hr_change=true".format(ids, currency)
    try:
        # CoinGecko blockt Anfragen ohne "beschreibenden" User-Agent mit 403.
        r = urequests.get(
            url, timeout=12,
            headers={"User-Agent": "MagicMirrorMini/1.0 (MicroPython; ESP32-S3)"},
        )
        data = r.json()
        r.close()
        prices = []
        for sym in symbols:
            entry = data.get(sym, {}) or {}
            prices.append({
                "id": sym,
                "price": entry.get(currency),
                "change24h": entry.get(currency + "_24h_change"),
                "currency": currency,
            })
        return {"ok": True, "prices": prices}
    except Exception as e:
        return {"ok": False, "msg": "Crypto error: {}".format(e), "prices": []}


def fetch_stocks(cfg):
    s = cfg["widgets"]["stocks"]
    symbols = s.get("symbols") or []
    if not symbols:
        return {"ok": False, "msg": "No symbols configured", "quotes": []}

    quotes = []
    for sym in symbols:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=5d&interval=1d".format(sym)
        try:
            r = urequests.get(
                url, timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (compatible; MagicMirrorMini/1.0)"},
            )
            data = r.json()
            r.close()
            result_list = ((data.get("chart") or {}).get("result")) or [None]
            result = result_list[0]
            if not result:
                quotes.append({"symbol": sym.upper(), "ok": False, "msg": "Not found"})
                continue
            meta = result.get("meta", {}) or {}
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
            if price is None:
                quotes.append({"symbol": sym.upper(), "ok": False, "msg": "No data"})
                continue
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else None
            currency_code = meta.get("currency") or ""
            quotes.append({
                "symbol": (meta.get("symbol") or sym).upper(),
                "price": price,
                "change24h": change_pct,
                "currency": CURRENCY_SYMBOLS.get(currency_code, currency_code),
                "ok": True,
            })
        except Exception as e:
            quotes.append({"symbol": sym.upper(), "ok": False, "msg": str(e)})
    return {"ok": True, "quotes": quotes}


def fetch_ews(cfg):
    try:
        data = _get_json(EWS_DASHBOARD_URL, timeout=15)
        cur = data.get("current", {}) or {}
        return {
            "ok": True,
            "emergency_level": cur.get("emergencyLevel"),
            "alert_level": cur.get("alertLevel"),
            "concurrent_count": cur.get("concurrentCount"),
            "baseline_mean": cur.get("baselineMean"),
            "z_score": cur.get("zScore"),
        }
    except Exception as e:
        return {"ok": False, "msg": "EWS unavailable: {}".format(e)}


def _tag_content(text, tag, start=0):
    """Sehr einfacher, hand-geschriebener XML-Tag-Extraktor (kein XML-Parser
    in MicroPython eingebaut). Reicht fuer die flache Struktur von RSS 2.0."""
    open_tag = "<" + tag
    close_tag = "</" + tag + ">"
    i = text.find(open_tag, start)
    if i == -1:
        return None, -1
    i = text.find(">", i)
    if i == -1:
        return None, -1
    i += 1
    j = text.find(close_tag, i)
    if j == -1:
        return None, -1
    return text[i:j], j + len(close_tag)


_TRANSLITERATE = {
    "\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue",
    "\u00c4": "Ae", "\u00d6": "Oe", "\u00dc": "Ue",
    "\u00df": "ss",
    "\u00e9": "e", "\u00e8": "e", "\u00ea": "e", "\u00e0": "a", "\u00e2": "a",
    "\u00e7": "c", "\u00f1": "n",
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...",
}


def _to_ascii(s):
    """Der Bitmap-Font des Displays erwartet einfache Einzelbyte-Zeichen.
    UTF-8-Mehrbyte-Zeichen (Umlaute, Anfuehrungszeichen, Gedankenstriche
    etc.) bringen das Zeichnen sonst mitten in der Zeile zum Stehen --
    daher vor der Anzeige in ASCII-Naeherungen umwandeln."""
    for k, v in _TRANSLITERATE.items():
        if k in s:
            s = s.replace(k, v)
    # alles, was danach noch nicht ASCII ist, durch "?" ersetzen statt
    # den Renderer damit zum Stocken zu bringen
    out = []
    for ch in s:
        out.append(ch if ord(ch) < 128 else "?")
    return "".join(out)


def _clean_xml_text(s):
    s = s.strip()
    if s.startswith("<![CDATA[") and s.endswith("]]>"):
        s = s[9:-3]
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    return _to_ascii(s.strip())


_news_source_idx = 0


def fetch_news(cfg):
    """Holt Schlagzeilen von einer RSS/Atom-Quelle. Reihum wird bei jedem
    Refresh eine andere konfigurierte Quelle geholt (wie das Original-
    Docker-Projekt), das Ergebnis wird als Lauftext angezeigt -- dadurch
    ist die Zeilenlaenge der Ueberschriften egal, es passt immer."""
    global _news_source_idx
    n = cfg["widgets"]["news"]
    sources = [s for s in (n.get("sources") or []) if (s.get("feedUrl") or "").strip()]
    if not sources:
        return {"ok": False, "msg": "No source configured", "items": [], "source_name": ""}

    idx = _news_source_idx % len(sources)
    _news_source_idx += 1
    src = sources[idx]
    name = src.get("name") or "News"
    url = src["feedUrl"].strip()
    max_items = int(n.get("max_items", 5) or 5)

    try:
        r = urequests.get(url, timeout=12)
        text = r.text
        r.close()
        items = []
        pos = 0
        while len(items) < max_items:
            block, next_pos = _tag_content(text, "item", pos)
            if block is None:
                break
            title, _ = _tag_content(block, "title")
            if title:
                items.append(_clean_xml_text(title))
            pos = next_pos
        return {"ok": True, "items": items, "source_name": name}
    except Exception as e:
        return {"ok": False, "msg": "News error: {}".format(e), "items": [], "source_name": name}


def _defcon_severity(value):
    """DEFCON principle: lower number = more critical."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    if v <= 2:
        return 7  # red
    if v <= 3.5:
        return 6  # amber
    return 0  # green/neutral


def fetch_defcon(cfg):
    d = cfg["widgets"]["defcon"]
    url = (d.get("url") or "").strip()
    api_key = (d.get("api_key") or "").strip()
    if not url:
        return {"ok": False, "msg": "No source URL configured", "regions": []}

    try:
        headers = {"X-API-Key": api_key} if api_key else {}
        r = urequests.get(url, headers=headers, timeout=10)
        data = r.json()
        r.close()
        regions = []
        for entry in data.get("regions", []) or []:
            name = entry.get("name")
            value = entry.get("value")
            if not name or value is None:
                continue
            regions.append({"name": name, "value": value, "severity": _defcon_severity(value)})
        return {"ok": True, "regions": regions}
    except Exception as e:
        return {"ok": False, "msg": "DEFCON error: {}".format(e), "regions": []}


# ---------------------------------------------------------------------
# Google Calendar (private iCal-Adresse, read-only, kein OAuth/API-Key)
#
# MicroPython hat keine icalendar-Bibliothek -- eigener, schlanker ICS-
# Zeilen-Parser. Wie im Docker-Projekt werden RRULE-Wiederholungen NICHT
# expandiert, nur der urspruengliche Starttermin jedes VEVENT wird
# beruecksichtigt (siehe README-Hinweis dort).
# ---------------------------------------------------------------------

def _unfold_ics(text):
    """Loest iCal-Zeilenumbrueche auf (Fortsetzungszeilen beginnen laut
    RFC 5545 mit einem Leerzeichen oder Tab)."""
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    for line in lines:
        if line and (line[0] == " " or line[0] == "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _ics_unescape(s):
    return (s.replace("\\n", " ").replace("\\N", " ")
             .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def _ics_split_line(line):
    if ":" not in line:
        return None, "", None
    left, value = line.split(":", 1)
    parts = left.split(";")
    return parts[0], ";".join(parts[1:]), value


def _parse_ics_dt(value, params, general):
    """Gibt (utc_epoch, all_day) zurueck, oder None bei Parse-Fehler."""
    value = value.strip()
    try:
        is_date_only = "VALUE=DATE" in params or (len(value) == 8 and value.isdigit())
        if is_date_only:
            y, mo, dd = int(value[0:4]), int(value[4:6]), int(value[6:8])
            return ntp_clock.local_wall_to_utc_epoch(y, mo, dd, 0, 0, 0, general), True

        is_utc = value.endswith("Z")
        v = value[:-1] if is_utc else value
        y, mo, dd = int(v[0:4]), int(v[4:6]), int(v[6:8])
        hh, mi, ss = int(v[9:11]), int(v[11:13]), int(v[13:15])
        if is_utc:
            epoch = time.mktime((y, mo, dd, hh, mi, ss, 0, 0))
        else:
            # Kein "Z" -> Wanduhrzeit, ggf. mit TZID-Parameter. Wir gehen
            # vereinfachend davon aus, dass der Kalender in derselben
            # Zeitzone wie das Geraet gefuehrt wird (kein volles
            # Zeitzonen-Datenbank-Handling auf dem Mikrocontroller).
            epoch = ntp_clock.local_wall_to_utc_epoch(y, mo, dd, hh, mi, ss, general)
        return epoch, False
    except Exception:
        return None


def fetch_calendar(cfg):
    c = cfg["widgets"]["calendar"]
    url = (c.get("icalUrl") or "").strip()
    if not url:
        return {"ok": False, "msg": "No iCal URL configured", "events": []}

    max_events = int(c.get("maxEvents", 5) or 5)
    days_ahead = int(c.get("daysAhead", 14) or 14)
    general = cfg.get("general", {})

    try:
        r = urequests.get(url, timeout=15)
        text = r.text
        r.close()
        lines = _unfold_ics(text)

        now_utc = time.time()
        window_start = now_utc - 20 * 3600
        horizon = now_utc + days_ahead * 86400

        events = []
        in_event = False
        cur = {}
        for line in lines:
            if line.startswith("BEGIN:VEVENT"):
                in_event = True
                cur = {}
                continue
            if line.startswith("END:VEVENT"):
                in_event = False
                dt = cur.get("dtstart")
                if dt is not None:
                    start_utc, all_day = dt
                    if window_start <= start_utc <= horizon:
                        events.append({
                            "title": cur.get("summary", "Untitled"),
                            "location": cur.get("location", ""),
                            "start_utc": start_utc,
                            "all_day": all_day,
                        })
                continue
            if not in_event:
                continue
            key, params, value = _ics_split_line(line)
            if key == "SUMMARY":
                cur["summary"] = _ics_unescape(value)
            elif key == "LOCATION":
                cur["location"] = _ics_unescape(value)
            elif key == "DTSTART":
                parsed = _parse_ics_dt(value, params, general)
                if parsed is not None:
                    cur["dtstart"] = parsed

        events.sort(key=lambda e: e["start_utc"])
        events = events[:max_events]
        for e in events:
            e["local"] = ntp_clock.local_time_from_epoch(e["start_utc"], general)

        return {"ok": True, "events": events}
    except Exception as e:
        return {"ok": False, "msg": "Calendar error: {}".format(e), "events": []}


# ---------------------------------------------------------------------
# Drawing functions: draw_<widget>(d, data) on a display.Display
# ---------------------------------------------------------------------

def _draw_header(d, title):
    """Centered heading in the accent color, no background box (just a
    thin divider line below) -- look and feel matches the Docker Magic
    Mirror project (.mm-widget-title in mirror.css)."""
    d.text_centered(title.upper(), disp.WIDTH // 2, 6, disp.ACCENT, size="medium")
    d.hline(50, 26, disp.WIDTH - 100, disp.ACCENT_DIM)


def _draw_error(d, title, msg):
    _draw_header(d, title)
    d.text_centered("No data", disp.WIDTH // 2, 74, disp.ALERT_RED, size="medium")
    d.text_centered(str(msg)[:40], disp.WIDTH // 2, 104, disp.FG_FAINT, size="small")


def draw_weather(d, data):
    if not data.get("ok"):
        _draw_error(d, "Weather", data.get("msg", "Error"))
        return
    title = "Weather"
    _draw_header(d, title)

    group = data.get("group")
    icon_fn = {
        "clear": d.icon_sun, "cloudy": d.icon_cloud, "rain": d.icon_rain,
        "snow": d.icon_snow, "storm": d.icon_storm, "fog": d.icon_fog,
    }.get(group, d.icon_cloud)
    icon_fn(60, 76, 28)

    temp = data.get("temperature")
    unit = data.get("unit", "C")
    temp_str = "{}\u00b0{}".format("{:.1f}".format(temp) if temp is not None else "--", unit)
    d.text(temp_str, 108, 38, disp.FG, size="large")
    d.text(data.get("description", ""), 108, 76, disp.FG_DIM, size="medium")

    feels = data.get("feels_like")
    hum = data.get("humidity")
    wind = data.get("wind")
    info = "Feels {}\u00b0  Hum {}%  Wind {} km/h".format(
        round(feels) if feels is not None else "--",
        round(hum) if hum is not None else "--",
        round(wind) if wind is not None else "--",
    )
    d.text_centered(info, disp.WIDTH // 2, 136, disp.FG_FAINT, size="small")

    warn = data.get("warning")
    if warn:
        d.text_centered(warn, disp.WIDTH // 2, 154, disp.AMBER, size="small")


def _aqi_color(aqi):
    if aqi is None:
        return disp.FG_DIM
    if aqi <= 40:
        return disp.UP
    if aqi <= 80:
        return disp.AMBER
    return disp.ALERT_RED


def draw_air_quality(d, data):
    if not data.get("ok"):
        _draw_error(d, "Air Quality", data.get("msg", "Error"))
        return
    title = "Air Quality"
    _draw_header(d, title)

    aqi = data.get("aqi")
    color = _aqi_color(aqi)
    cx, cy, r = 62, 74, 34
    d.circle_fill(cx, cy, r, color)
    # WICHTIG: bg=color statt Standard-Schwarz, sonst zeichnet text() einen
    # deckenden schwarzen Kasten hinter jedem Zeichen -- sichtbar als
    # schwarzes Viereck mitten im farbigen Kreis.
    aqi_str = str(aqi) if aqi is not None else "--"
    d.text_centered(aqi_str, cx, cy - 16, disp.BLACK, size="large", bg=color)
    d.text_centered("EU-AQI", cx, cy + r + 10, disp.FG_FAINT, size="small")

    rows = [
        ("PM2.5", data.get("pm25")),
        ("PM10", data.get("pm10")),
        ("Ozone", data.get("ozone")),
    ]
    y = 40
    for label, value in rows:
        val_str = "{} ug/m3".format(round(value, 1) if value is not None else "--")
        d.text(label, 146, y, disp.FG_DIM, size="small")
        d.text(val_str, 146, y + 13, disp.FG, size="medium")
        y += 38


def draw_warnings(d, data):
    title = "Warnings"
    _draw_header(d, title)

    if not data.get("ok"):
        _draw_error(d, "Warnings", data.get("msg", "Error"))
        return

    warnings = data.get("warnings", [])
    if not warnings:
        d.icon_sun(disp.WIDTH // 2, 88, 22, disp.UP)
        d.text_centered("No active warnings", disp.WIDTH // 2, 134, disp.UP, size="small")
        return

    y = 42
    for w in warnings[:4]:
        sev = w.get("severity", 0)
        color = disp.ALERT_RED if sev >= 7 else disp.AMBER
        d.rect(24, y + 2, 9, 9, color, fill=True)
        title_txt = w.get("title", "")[:42]
        d.text(title_txt, 42, y, disp.FG, size="small")
        y += 24
        if y > HEIGHT_LIMIT:
            break


HEIGHT_LIMIT = 165


def _change_color(change):
    if change is None:
        return disp.FG_DIM
    return disp.UP if change >= 0 else disp.DOWN


def draw_crypto(d, data):
    _draw_header(d, "Crypto")

    if not data.get("ok"):
        _draw_error(d, "Crypto", data.get("msg", "Error"))
        return

    prices = data.get("prices", [])
    if not prices:
        d.text_centered("No coins configured", disp.WIDTH // 2, 80, disp.FG_FAINT, size="small")
        return

    y = 40
    for p in prices[:4]:
        name = p.get("id", "?")[:12].upper()
        price = p.get("price")
        change = p.get("change24h")
        currency = (p.get("currency") or "").upper()
        price_str = "{} {}".format(round(price, 2) if price is not None else "--", currency)
        change_str = "{}{}%".format("+" if (change or 0) >= 0 else "", round(change, 1) if change is not None else "--")

        d.text(name, 16, y, disp.FG_DIM, size="small")
        d.text(price_str, 16, y + 14, disp.FG, size="medium")
        d.text(change_str, 196, y + 14, _change_color(change), size="medium")
        y += 36


def draw_stocks(d, data):
    _draw_header(d, "Stocks")

    if not data.get("ok"):
        _draw_error(d, "Stocks", data.get("msg", "Error"))
        return

    quotes = data.get("quotes", [])
    if not quotes:
        d.text_centered("No symbols configured", disp.WIDTH // 2, 80, disp.FG_FAINT, size="small")
        return

    y = 40
    for q in quotes[:4]:
        symbol = q.get("symbol", "?")[:10]
        if not q.get("ok"):
            d.text(symbol, 16, y, disp.FG_DIM, size="small")
            d.text(q.get("msg", "Error")[:20], 16, y + 14, disp.ALERT_RED, size="small")
            y += 36
            continue
        price = q.get("price")
        change = q.get("change24h")
        currency = q.get("currency", "")
        price_str = "{}{}".format(round(price, 2) if price is not None else "--", currency)
        change_str = "{}{}%".format("+" if (change or 0) >= 0 else "", round(change, 1) if change is not None else "--")

        d.text(symbol, 16, y, disp.FG_DIM, size="small")
        d.text(price_str, 16, y + 14, disp.FG, size="medium")
        d.text(change_str, 196, y + 14, _change_color(change), size="medium")
        y += 36


def _ews_color(level):
    if level is None:
        return disp.FG_DIM
    if level >= 4:
        return disp.ALERT_RED
    if level >= 3:
        return disp.AMBER
    return disp.UP


def draw_ews(d, data):
    _draw_header(d, "Apocalypse EWS")

    if not data.get("ok"):
        _draw_error(d, "Apocalypse EWS", data.get("msg", "Error"))
        return

    level = data.get("emergency_level")
    color = _ews_color(level)
    level_str = str(level) if level is not None else "--"
    d.text_centered(level_str, disp.WIDTH // 2, 46, color, size="large")
    d.text_centered("EMERGENCY LEVEL (1-5)", disp.WIDTH // 2, 96, disp.FG_FAINT, size="small")

    count = data.get("concurrent_count")
    baseline = data.get("baseline_mean")
    stats = "Airborne {}  Baseline {}".format(
        count if count is not None else "--",
        round(baseline, 1) if baseline is not None else "--",
    )
    d.text_centered(stats, disp.WIDTH // 2, 122, disp.FG_DIM, size="small")


def draw_defcon(d, data):
    _draw_header(d, "DEFCON")

    if not data.get("ok"):
        _draw_error(d, "DEFCON", data.get("msg", "Error"))
        return

    regions = data.get("regions", [])
    if not regions:
        d.text_centered("No regions configured", disp.WIDTH // 2, 80, disp.FG_FAINT, size="small")
        return

    cols = 2
    col_w = disp.WIDTH // cols
    for i, r in enumerate(regions[:6]):
        col = i % cols
        row = i // cols
        x = 16 + col * col_w
        y = 38 + row * 34
        sev = r.get("severity", 0)
        color = disp.ALERT_RED if sev == 7 else disp.AMBER if sev == 6 else disp.UP
        d.text(r.get("name", "?")[:14], x, y, disp.FG_DIM, size="small")
        val = r.get("value")
        d.text(str(val) if val is not None else "--", x, y + 14, color, size="medium")


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def draw_calendar(d, data):
    _draw_header(d, "Calendar")

    if not data.get("ok"):
        _draw_error(d, "Calendar", data.get("msg", "Error"))
        return

    events = data.get("events", [])
    if not events:
        d.text_centered("No upcoming events", disp.WIDTH // 2, 80, disp.UP, size="small")
        return

    y = 36
    for e in events[:3]:
        lt = e.get("local")
        if lt:
            wd = WEEKDAYS_SHORT[lt[6]]
            date_part = "{} {:02d}.{:02d}".format(wd, lt[2], lt[1])
            time_part = "all day" if e.get("all_day") else "{:02d}:{:02d}".format(lt[3], lt[4])
            d.text("{}  {}".format(date_part, time_part), 14, y, disp.ACCENT, size="small")
        title = (e.get("title") or "Untitled")[:19]
        d.text(title, 14, y + 14, disp.FG, size="medium")
        y += 42
        if y > HEIGHT_LIMIT:
            break


def draw_clock(d, cfg):
    lt, dst = ntp_clock.local_time(cfg)
    year, month, mday, hour, minute, second, weekday, yearday = lt

    general = cfg.get("general", {})
    hour24 = general.get("hour24", True)
    show_seconds = general.get("show_seconds", True)

    ampm = ""
    h = hour
    if not hour24:
        ampm = "AM" if hour < 12 else "PM"
        h = hour % 12
        if h == 0:
            h = 12

    if show_seconds:
        time_str = "{:02d}:{:02d}:{:02d}".format(h, minute, second)
    else:
        time_str = "{:02d}:{:02d}".format(h, minute)

    d.clear(disp.BLACK)

    # Vektor-Font (Linienzuege statt Pixel-Bitmap) fuer eine grosse,
    # glatt skalierende Uhrzeit -- keine Blockpixel-Optik.
    scale = d.fit_vector_scale(CLOCK_FONT, time_str, disp.WIDTH - 24, max_scale=5.5)
    w = d.vector_width(CLOCK_FONT, time_str, scale)
    x = (disp.WIDTH - w) // 2
    d.draw_vector(CLOCK_FONT, time_str, x, 72, disp.FG, scale=scale)

    if ampm:
        d.text(ampm, x + w + 8, 40, disp.FG_DIM, size="medium")

    date_str = "{}, {:02d}.{:02d}.{:04d}".format(WEEKDAYS[weekday], mday, month, year)
    d.text_centered(date_str, disp.WIDTH // 2, 106, disp.FG_DIM, size="medium")

    if dst:
        d.text_centered("Daylight Saving Time", disp.WIDTH // 2, 136, disp.ACCENT, size="small")
    if not ntp_clock.is_synced():
        d.text_centered("NTP not synced", disp.WIDTH // 2, 136, disp.ALERT_RED, size="small")


# ---------------------------------------------------------------------
# News-Ticker: laeuft als horizontaler Lauftext durch, damit egal wie
# lang eine Schlagzeile ist, sie nie abgeschnitten werden muss -- passt
# damit garantiert gut aufs kleine Display. main.py ruft draw_news() alle
# ~150ms erneut auf, solange News das aktuell gezeigte Widget ist.
#
# WICHTIG: der s3lcd-Text-Renderer kommt mit NEGATIVEN x-Koordinaten nicht
# klar -- er "wrapped" den Text zyklisch statt ihn sauber abzuschneiden
# (das Ende landet vorn). Deshalb wird hier NIE mit negativem x gezeichnet,
# sondern zeichenweise durch einen doppelt aneinandergehaengten Text
# geschoben (immer bei x=0), das ist fuer diesen Treiber sicher.
# ---------------------------------------------------------------------
_news_char_offset = 0
_news_ticker_text = ""
TICKER_SEPARATOR = "     \u2022     "
TICKER_CHAR_W = 16       # Breite eines Zeichens im "medium"-Bitmap-Font
TICKER_CHARS_PER_TICK = 1  # main.py ruft alle ~150ms auf -> ca. 107 Zeichen/s * 16px = ~107px/s
TICKER_Y = 82


def _build_ticker_text(items, source_name):
    body = TICKER_SEPARATOR.join(items) if items else "No headlines"
    if source_name:
        body = source_name.upper() + ":  " + body
    return body + "          "  # kleine Luecke, bevor der Text von vorn beginnt


def draw_news(d, data):
    global _news_char_offset, _news_ticker_text
    _draw_header(d, "News")

    if not data.get("ok"):
        _draw_error(d, "News", data.get("msg", "Error"))
        _news_char_offset = 0
        return

    text = _build_ticker_text(data.get("items", []), data.get("source_name", ""))

    if text != _news_ticker_text:
        _news_ticker_text = text
        _news_char_offset = 0

    # WICHTIG: hier NICHT mehr Zeichen zeichnen als tatsaechlich auf den
    # Bildschirm passen -- der Treiber schneidet Ueberschuss ueber die
    # Displaybreite hinaus nicht sauber ab, sondern wickelt ihn an den
    # linken Rand (derselbe Wrap-Effekt wie bei negativem x). 320/16=20
    # passt exakt, keine Sicherheitsmarge noetig.
    visible_chars = disp.WIDTH // TICKER_CHAR_W
    reps = (visible_chars // max(1, len(text))) + 2
    doubled = text * reps  # nahtloser Uebergang beim Wiederholen, auch bei kurzen Texten
    start = _news_char_offset % len(text)
    visible_text = doubled[start:start + visible_chars]

    d.text(visible_text, 0, TICKER_Y, disp.FG, size="medium")

    _news_char_offset += TICKER_CHARS_PER_TICK


# ---------------------------------------------------------------------
# Compliments: rein lokal, kein Netzwerk noetig -- zufaelliger Spruch aus
# einer im Web-UI frei editierbaren Liste.
# ---------------------------------------------------------------------

def _wrap_lines(d, text, size, max_width, max_lines=3):
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = (cur + " " + word).strip()
        if d.text_width(trial, size) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def draw_compliments(d, cfg):
    _draw_header(d, "Compliments")

    comp_cfg = cfg.get("widgets", {}).get("compliments", {})
    messages = comp_cfg.get("messages") or ["You're doing great!"]
    msg = messages[random.randrange(len(messages))]

    lines = _wrap_lines(d, msg, "medium", disp.WIDTH - 40, max_lines=3)
    total_h = len(lines) * 22
    y = max(56, (disp.HEIGHT - total_h) // 2)
    for line in lines:
        d.text_centered(line, disp.WIDTH // 2, y, disp.ACCENT, size="medium")
        y += 22
