"""Leichtgewichtiger HTTP-Server (uasyncio) fuer das Web-Setup.

Laeuft parallel zur Spiegelanzeige. Bietet:
  GET  /                -> Einstellungsseite (HTML, eingebettet)
  GET  /api/config      -> aktuelle Konfiguration als JSON
  POST /api/config      -> Konfiguration speichern (JSON-Body)
  GET  /api/geocode     -> Ortssuche fuer Wetter/Luftqualitaet (?q=...)
  GET  /api/ags-search  -> Ortssuche fuer NINA-Warnungen (?q=...)
  GET  /api/wifi-scan   -> verfuegbare WLAN-Netze
  POST /api/restart     -> Geraet neu starten
"""

import uasyncio as asyncio
import ujson as json
import network
import machine

import config_store
import widgets

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Magic Mirror Mini – Settings</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#111318; color:#eee;
         margin:0; padding:20px; max-width:640px; margin-inline:auto; }
  h1 { font-size:1.3rem; }
  h2 { font-size:1rem; color:#9ad; margin-top:28px; border-bottom:1px solid #333; padding-bottom:6px; }
  label { display:block; margin-top:10px; font-size:0.85rem; color:#bbb; }
  input, select { width:100%; box-sizing:border-box; padding:8px; margin-top:4px; border-radius:6px;
                  border:1px solid #333; background:#1c1f26; color:#eee; font-size:0.95rem; }
  .row { display:flex; gap:10px; }
  .row > div { flex:1; }
  button { margin-top:16px; padding:10px 16px; border:none; border-radius:6px; background:#3d7fff;
           color:white; font-size:0.95rem; cursor:pointer; }
  button.secondary { background:#333; }
  .search-results { margin-top:6px; }
  .search-results div { padding:8px; background:#1c1f26; border-radius:6px; margin-top:4px; cursor:pointer; }
  .search-results div:hover { background:#26304a; }
  #status { margin-top:14px; font-size:0.9rem; }
  .hint { font-size:0.78rem; color:#777; margin-top:4px; }
  .card { background:#181b22; border-radius:10px; padding:14px; margin-top:14px; }
</style>
</head>
<body>
<h1>🪞 Magic Mirror Mini</h1>
<div id="status"></div>

<div class="card">
<h2>Widgets</h2>
<div class="hint">Turn individual widgets on or off in the rotation.</div>
<label style="display:flex;align-items:center;gap:8px;margin-top:10px">
  <input id="w_clock" type="checkbox" style="width:auto"> Clock
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_weather" type="checkbox" style="width:auto"> Weather
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_air_quality" type="checkbox" style="width:auto"> Air Quality
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_warnings" type="checkbox" style="width:auto"> Official Warnings (NINA)
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_calendar" type="checkbox" style="width:auto"> Calendar
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_news" type="checkbox" style="width:auto"> News
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_crypto" type="checkbox" style="width:auto"> Crypto
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_stocks" type="checkbox" style="width:auto"> Stocks
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_ews" type="checkbox" style="width:auto"> Apocalypse EWS
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_defcon" type="checkbox" style="width:auto"> DEFCON
</label>
<label style="display:flex;align-items:center;gap:8px;margin-top:8px">
  <input id="w_compliments" type="checkbox" style="width:auto"> Compliments
</label>
</div>

<div class="card">
<h2>WiFi</h2>
<label>SSID</label>
<input id="wifi_ssid">
<label>Password</label>
<input id="wifi_password" type="password">
<div class="hint">Without a valid WiFi network, the device opens the setup access point below again on next restart.</div>
</div>

<div class="card">
<h2>Setup Access Point</h2>
<div class="hint">Name/password of the access point the device opens when it has no working WiFi (or you're seeing this page through it right now).</div>
<label>AP SSID</label>
<input id="ap_ssid">
<label>AP Password (min. 8 characters, leave short/empty for an open network)</label>
<input id="ap_password">
</div>


<div class="card">
<h2>Clock</h2>
<div class="row">
  <div><label>UTC offset (hours)</label><input id="utc_offset" type="number"></div>
  <div><label>Time format</label>
    <select id="hour24"><option value="true">24-hour</option><option value="false">12-hour (AM/PM)</option></select>
  </div>
</div>
<label><input id="dst_auto" type="checkbox" style="width:auto;display:inline"> Automatic daylight saving (EU rule)</label>
<label><input id="show_seconds" type="checkbox" style="width:auto;display:inline"> Show seconds</label>
</div>

<div class="card">
<h2>Weather</h2>
<label>Search location</label>
<input id="weather_search" placeholder="e.g. Hamburg">
<div class="search-results" id="weather_results"></div>
<div class="hint" id="weather_selected"></div>
<label>Unit</label>
<select id="weather_units"><option value="celsius">°C</option><option value="fahrenheit">°F</option></select>
</div>

<div class="card">
<h2>Air Quality</h2>
<label>Search location</label>
<input id="aq_search" placeholder="e.g. Hamburg">
<div class="search-results" id="aq_results"></div>
<div class="hint" id="aq_selected"></div>
</div>

<div class="card">
<h2>Official Warnings (NINA)</h2>
<label>Search location / postal code</label>
<input id="warn_search" placeholder="e.g. 20095 or Hamburg">
<div class="search-results" id="warn_results"></div>
<div class="hint" id="warn_selected"></div>
</div>

<div class="card">
<h2>Calendar (Google, private iCal address)</h2>
<label>Private iCal URL</label>
<input id="calendar_url" placeholder="https://calendar.google.com/calendar/ical/.../private-.../basic.ics">
<div class="hint">Google Calendar → Settings → your calendar → "Integrate calendar" → "Secret address in iCal format".</div>
<div class="row">
  <div><label>Max. events shown</label><input id="calendar_max" type="number"></div>
  <div><label>Look ahead (days)</label><input id="calendar_days" type="number"></div>
</div>
</div>

<div class="card">
<h2>News (RSS)</h2>
<div class="hint">Up to 3 feeds, rotated one per refresh cycle. Shown as a scrolling ticker, so headline length doesn't matter.</div>
<div class="row">
  <div><label>Source 1 name</label><input id="news1_name"></div>
  <div style="flex:2"><label>Source 1 feed URL</label><input id="news1_url"></div>
</div>
<div class="row">
  <div><label>Source 2 name</label><input id="news2_name"></div>
  <div style="flex:2"><label>Source 2 feed URL</label><input id="news2_url"></div>
</div>
<div class="row">
  <div><label>Source 3 name</label><input id="news3_name"></div>
  <div style="flex:2"><label>Source 3 feed URL</label><input id="news3_url"></div>
</div>
</div>

<div class="card">
<h2>Compliments</h2>
<div class="hint">One message per line. Runs locally, no network needed. A random one is shown each time.</div>
<textarea id="compliments_messages" rows="6" style="width:100%; box-sizing:border-box; padding:8px; margin-top:4px; border-radius:6px; border:1px solid #333; background:#1c1f26; color:#eee; font-size:0.95rem;"></textarea>
</div>

<div class="card">
<h2>Crypto</h2>
<label>Coin IDs (CoinGecko, comma-separated, e.g. bitcoin,ethereum,solana)</label>

<input id="crypto_symbols">
<label>Currency</label>
<select id="crypto_currency"><option value="usd">USD</option><option value="eur">EUR</option></select>
</div>

<div class="card">
<h2>Stocks</h2>
<label>Symbols (Yahoo Finance format, comma-separated, e.g. AAPL,SAP.DE)</label>
<input id="stocks_symbols">
</div>

<div class="card">
<h2>DEFCON</h2>
<div class="hint">Built for <a href="https://ai-defcon.com" target="_blank" style="color:#9ad">ai-defcon.com</a> — see that site for how to get your endpoint URL and API key. Any endpoint returning the same JSON shape works too.</div>
<label>Source URL</label>
<input id="defcon_url" placeholder="https://ai-defcon.com/api/status.json">
<label>API key (optional, sent as X-API-Key header)</label>
<input id="defcon_api_key" type="password">
</div>

<div class="card">
<h2>Display</h2>
<label>Cycle interval (seconds per widget)</label>
<input id="cycle_seconds" type="number">
<label>Data refresh (minutes)</label>
<input id="refresh_minutes" type="number">
</div>

<button onclick="save()">Save</button>
<button class="secondary" onclick="restart()">Restart</button>

<script>
let weatherSel = null, aqSel = null, warnSel = null;

const WIDGET_NAMES = ['clock', 'weather', 'air_quality', 'warnings', 'calendar', 'news', 'crypto', 'stocks', 'ews', 'defcon', 'compliments'];

async function load() {
  const cfg = await (await fetch('/api/config')).json();

  WIDGET_NAMES.forEach(name => {
    const w = cfg.widgets[name] || {};
    const el = document.getElementById('w_' + name);
    if (el) el.checked = w.enabled !== false;
  });

  document.getElementById('wifi_ssid').value = cfg.wifi.ssid || '';
  document.getElementById('wifi_password').value = cfg.wifi.password || '';

  const ap = cfg.ap || {};
  document.getElementById('ap_ssid').value = ap.ssid || '';
  document.getElementById('ap_password').value = ap.password || '';

  document.getElementById('utc_offset').value = cfg.general.utc_offset;
  document.getElementById('hour24').value = String(cfg.general.hour24);
  document.getElementById('dst_auto').checked = cfg.general.dst_auto;
  document.getElementById('show_seconds').checked = cfg.general.show_seconds;
  document.getElementById('cycle_seconds').value = cfg.general.cycle_seconds;
  document.getElementById('refresh_minutes').value = cfg.general.refresh_minutes;

  const w = cfg.widgets.weather;
  weatherSel = { location: w.location, latitude: w.latitude, longitude: w.longitude };
  document.getElementById('weather_selected').innerText = 'Current: ' + (w.location || 'none');
  document.getElementById('weather_units').value = w.units;

  const a = cfg.widgets.air_quality;
  aqSel = { location: a.location, latitude: a.latitude, longitude: a.longitude };
  document.getElementById('aq_selected').innerText = 'Current: ' + (a.location || 'none');

  const n = cfg.widgets.warnings;
  warnSel = { location: n.location, ars: n.ars };
  document.getElementById('warn_selected').innerText = 'Current: ' + (n.location || 'no location selected yet');

  const cal = cfg.widgets.calendar || {};
  document.getElementById('calendar_url').value = cal.icalUrl || '';
  document.getElementById('calendar_max').value = cal.maxEvents || 5;
  document.getElementById('calendar_days').value = cal.daysAhead || 14;

  const news = (cfg.widgets.news && cfg.widgets.news.sources) || [];
  for (let i = 0; i < 3; i++) {
    const src = news[i] || {};
    document.getElementById('news' + (i + 1) + '_name').value = src.name || '';
    document.getElementById('news' + (i + 1) + '_url').value = src.feedUrl || '';
  }

  const compliments = cfg.widgets.compliments || {};
  document.getElementById('compliments_messages').value = (compliments.messages || []).join(String.fromCharCode(10));

  const crypto = cfg.widgets.crypto || {};
  document.getElementById('crypto_symbols').value = (crypto.symbols || []).join(',');
  document.getElementById('crypto_currency').value = crypto.currency || 'usd';

  const stocks = cfg.widgets.stocks || {};
  document.getElementById('stocks_symbols').value = (stocks.symbols || []).join(',');

  const defcon = cfg.widgets.defcon || {};
  document.getElementById('defcon_url').value = defcon.url || '';
  document.getElementById('defcon_api_key').value = defcon.api_key || '';
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

async function searchWeatherLike(q, resultsEl, onPick) {
  resultsEl.innerHTML = '';
  if (!q || q.length < 2) return;
  const res = await (await fetch('/api/geocode?q=' + encodeURIComponent(q))).json();
  (res.results || []).forEach(r => {
    const div = document.createElement('div');
    div.innerText = r.label;
    div.onclick = () => onPick(r);
    resultsEl.appendChild(div);
  });
}

async function searchWarnings(q) {
  const resultsEl = document.getElementById('warn_results');
  resultsEl.innerHTML = '';
  if (!q || q.length < 2) return;
  const res = await (await fetch('/api/ags-search?q=' + encodeURIComponent(q))).json();
  (res.results || []).forEach(r => {
    const div = document.createElement('div');
    div.innerText = r.label;
    div.onclick = () => {
      warnSel = { location: r.label, ars: r.ars };
      document.getElementById('warn_selected').innerText = 'Selected: ' + r.label;
      resultsEl.innerHTML = '';
      document.getElementById('warn_search').value = '';
    };
    resultsEl.appendChild(div);
  });
}

document.getElementById('weather_search').addEventListener('input', debounce(e => {
  searchWeatherLike(e.target.value, document.getElementById('weather_results'), r => {
    weatherSel = { location: r.label, latitude: r.latitude, longitude: r.longitude };
    document.getElementById('weather_selected').innerText = 'Selected: ' + r.label;
    document.getElementById('weather_results').innerHTML = '';
    document.getElementById('weather_search').value = '';
  });
}, 400));

document.getElementById('aq_search').addEventListener('input', debounce(e => {
  searchWeatherLike(e.target.value, document.getElementById('aq_results'), r => {
    aqSel = { location: r.label, latitude: r.latitude, longitude: r.longitude };
    document.getElementById('aq_selected').innerText = 'Selected: ' + r.label;
    document.getElementById('aq_results').innerHTML = '';
    document.getElementById('aq_search').value = '';
  });
}, 400));

document.getElementById('warn_search').addEventListener('input', debounce(e => {
  searchWarnings(e.target.value);
}, 400));

async function save() {
  const cfg = await (await fetch('/api/config')).json();

  WIDGET_NAMES.forEach(name => {
    cfg.widgets[name] = cfg.widgets[name] || {};
    const el = document.getElementById('w_' + name);
    if (el) cfg.widgets[name].enabled = el.checked;
  });

  cfg.wifi.ssid = document.getElementById('wifi_ssid').value;
  cfg.wifi.password = document.getElementById('wifi_password').value;

  cfg.ap = cfg.ap || {};
  cfg.ap.ssid = document.getElementById('ap_ssid').value.trim() || 'MagicMirror-Setup';
  cfg.ap.password = document.getElementById('ap_password').value;

  cfg.general.utc_offset = parseInt(document.getElementById('utc_offset').value || '0');
  cfg.general.hour24 = document.getElementById('hour24').value === 'true';
  cfg.general.dst_auto = document.getElementById('dst_auto').checked;
  cfg.general.show_seconds = document.getElementById('show_seconds').checked;
  cfg.general.cycle_seconds = parseInt(document.getElementById('cycle_seconds').value || '8');
  cfg.general.refresh_minutes = parseInt(document.getElementById('refresh_minutes').value || '10');

  if (weatherSel) Object.assign(cfg.widgets.weather, weatherSel);
  cfg.widgets.weather.units = document.getElementById('weather_units').value;
  if (aqSel) Object.assign(cfg.widgets.air_quality, aqSel);
  if (warnSel) Object.assign(cfg.widgets.warnings, warnSel);

  cfg.widgets.calendar = cfg.widgets.calendar || {};
  cfg.widgets.calendar.icalUrl = document.getElementById('calendar_url').value.trim();
  cfg.widgets.calendar.maxEvents = parseInt(document.getElementById('calendar_max').value || '5');
  cfg.widgets.calendar.daysAhead = parseInt(document.getElementById('calendar_days').value || '14');

  const newsSources = [];
  for (let i = 1; i <= 3; i++) {
    const srcName = document.getElementById('news' + i + '_name').value.trim();
    const srcUrl = document.getElementById('news' + i + '_url').value.trim();
    if (srcUrl) newsSources.push({ name: srcName || ('Source ' + i), feedUrl: srcUrl });
  }
  cfg.widgets.news = cfg.widgets.news || {};
  cfg.widgets.news.sources = newsSources;
  cfg.widgets.news.max_items = cfg.widgets.news.max_items || 5;

  cfg.widgets.compliments = cfg.widgets.compliments || {};
  cfg.widgets.compliments.messages = document.getElementById('compliments_messages').value
    .split(String.fromCharCode(10)).map(s => s.trim()).filter(Boolean);

  cfg.widgets.crypto = cfg.widgets.crypto || {};
  cfg.widgets.crypto.symbols = document.getElementById('crypto_symbols').value
    .split(',').map(s => s.trim()).filter(Boolean);
  cfg.widgets.crypto.currency = document.getElementById('crypto_currency').value;

  cfg.widgets.stocks = cfg.widgets.stocks || {};
  cfg.widgets.stocks.symbols = document.getElementById('stocks_symbols').value
    .split(',').map(s => s.trim()).filter(Boolean);

  cfg.widgets.defcon = cfg.widgets.defcon || {};
  cfg.widgets.defcon.url = document.getElementById('defcon_url').value.trim();
  cfg.widgets.defcon.api_key = document.getElementById('defcon_api_key').value.trim();

  const r = await fetch('/api/config', { method: 'POST', body: JSON.stringify(cfg) });
  document.getElementById('status').innerText = r.ok ? '✅ Saved.' : '❌ Error while saving.';
}

async function restart() {
  document.getElementById('status').innerText = 'Restarting...';
  await fetch('/api/restart', { method: 'POST' });
}

load();
</script>
</body>
</html>
"""


async def _write_all(writer, data):
    """Sendet data zuverlaessig in kleinen Chunks mit explizitem drain()
    dazwischen. writer.awrite() allein hat sich bei grossen Payloads
    (z.B. der ~14 KB grossen INDEX_HTML-Seite) als unzuverlaessig
    erwiesen -- Teile der Antwort kamen beim Client verstuemmelt/
    unvollstaendig an."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    chunk_size = 512
    mv = memoryview(data)
    for i in range(0, len(mv), chunk_size):
        writer.write(mv[i:i + chunk_size])
        await writer.drain()


async def _json_response(writer, obj, status=200):
    body = json.dumps(obj)
    await _send(writer, status, "application/json", body)


async def _send(writer, status, content_type, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    header = "HTTP/1.0 {} OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(
        status, content_type, len(body)
    )
    await _write_all(writer, header)
    await _write_all(writer, body)


async def _read_request(reader):
    request_line = await reader.readline()
    if not request_line:
        return None, None, {}, b""
    try:
        method, path, _ = request_line.decode().split(" ", 2)
    except ValueError:
        return None, None, {}, b""

    headers = {}
    while True:
        line = await reader.readline()
        if not line or line == b"\r\n":
            break
        try:
            k, v = line.decode().split(":", 1)
            headers[k.strip().lower()] = v.strip()
        except ValueError:
            pass

    body = b""
    length = int(headers.get("content-length", 0))
    if length:
        body = await reader.readexactly(length)

    return method, path, headers, body


def _query_param(path, name):
    if "?" not in path:
        return ""
    q = path.split("?", 1)[1]
    for pair in q.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k == name:
                # sehr einfaches URL-Decoding, reicht fuer Ortsnamen/PLZ
                v = v.replace("+", " ")
                out = ""
                i = 0
                while i < len(v):
                    if v[i] == "%" and i + 2 < len(v):
                        out += chr(int(v[i + 1:i + 3], 16))
                        i += 3
                    else:
                        out += v[i]
                        i += 1
                return out
    return ""


async def handle_client(reader, writer):
    try:
        method, path, headers, body = await _read_request(reader)
        if method is None:
            return

        route = path.split("?", 1)[0]

        if method == "GET" and route == "/":
            await _write_all(
                writer,
                "HTTP/1.0 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                "Cache-Control: no-store, no-cache, must-revalidate\r\n"
                "Connection: close\r\n\r\n",
            )
            await _write_all(writer, INDEX_HTML)

        elif method == "GET" and route == "/api/config":
            cfg = config_store.load_config()
            await _json_response(writer, cfg)

        elif method == "POST" and route == "/api/config":
            try:
                new_cfg = json.loads(body)
                config_store.save_config(new_cfg)
                await _json_response(writer, {"ok": True})
            except Exception as e:
                await _json_response(writer, {"ok": False, "msg": str(e)}, status=400)

        elif method == "GET" and route == "/api/geocode":
            q = _query_param(path, "q")
            try:
                results = widgets.geocode_search(q) if q else []
                await _json_response(writer, {"ok": True, "results": results})
            except Exception as e:
                await _json_response(writer, {"ok": False, "msg": str(e), "results": []})

        elif method == "GET" and route == "/api/ags-search":
            q = _query_param(path, "q")
            try:
                results = widgets.ags_search(q) if q else []
                await _json_response(writer, {"ok": True, "results": results})
            except Exception as e:
                await _json_response(writer, {"ok": False, "msg": str(e), "results": []})

        elif method == "GET" and route == "/api/wifi-scan":
            try:
                sta = network.WLAN(network.STA_IF)
                sta.active(True)
                nets = sta.scan()
                results = sorted(
                    [{"ssid": n[0].decode(), "rssi": n[3]} for n in nets if n[0]],
                    key=lambda x: -x["rssi"],
                )
                await _json_response(writer, {"ok": True, "networks": results})
            except Exception as e:
                await _json_response(writer, {"ok": False, "msg": str(e), "networks": []})

        elif method == "POST" and route == "/api/restart":
            await _json_response(writer, {"ok": True})
            try:
                await writer.aclose()
            except Exception:
                pass
            await asyncio.sleep(0.5)
            machine.reset()

        else:
            await _send(writer, 404, "text/plain", "Not found")

    except Exception as e:
        try:
            await _send(writer, 500, "text/plain", "Server error: {}".format(e))
        except Exception:
            pass
    finally:
        try:
            await writer.aclose()
        except Exception:
            pass


async def start(port=80):
    await asyncio.start_server(handle_client, "0.0.0.0", port)
    print("Web-Setup laeuft auf Port", port)
