# Magic Mirror Mini – T-Display S3

*[Deutsche Version / German version: README_de.md](README_de.md)*

A MicroPython project for the LilyGO **T-Display S3** (ESP32-S3, 1.9" ST7789,
320×170) that turns the board into a tiny "magic mirror" style dashboard.
Widgets rotate automatically on the small screen; WiFi and every widget's
settings are configured through a built-in web UI — no cloud service, no
app, no API keys anywhere.

This is a compact port of a larger Docker-based Magic Mirror dashboard
project; the picture below shows that original, bigger dashboard which
inspired the widget selection and data sources used here.

![Original Magic Mirror dashboard that inspired this project](pictures/1.png)

## Widgets

| Widget | Source | Details |
|---|---|---|
| Clock | NTP (`pool.ntp.org`) | Second-accurate, automatic EU daylight saving, 12/24h switchable |
| Weather | Open-Meteo | Temperature, feels-like, wind, humidity, storm/heat/cold warning line |
| Air Quality | Open-Meteo Air Quality | EU-AQI (color-coded), PM2.5, PM10, ozone |
| Official Warnings | warnung.bund.de (NINA/BBK, Germany) | DWD severe weather + civil protection alerts for the selected district |
| Calendar | Google Calendar (private iCal address) | Up to 5 upcoming events, 14-day look-ahead, no RRULE expansion |
| Crypto | CoinGecko | Up to 4 coins, price + 24h change |
| Stocks | Yahoo Finance chart endpoint | Up to 4 symbols, price + 24h change |
| Apocalypse EWS | ews.kylemcdonald.net snapshot feed | Alert level 1–5, tracked-jet count vs. learned baseline |
| DEFCON | your own JSON endpoint (e.g. ai-defcon.com) | Region list, color-coded (lower number = more critical) |

Every widget can be turned on or off individually in the web UI. All data
sources are free and require no API key.

## ⚠️ Important: this display is not SPI

The T-Display S3 does not connect its ST7789 panel over SPI like most
"generic" ESP32 boards — it uses an **8-bit parallel bus (Intel 8080 / i80)**.
The common `st7789py`/`st7789_mpy` drivers (SPI-only) will **not** work.
This project uses the [`s3lcd`](https://github.com/russhughes/s3lcd) driver
by russhughes instead, which is built specifically for this bus. That means
you need a **special MicroPython firmware**, not the stock build from
micropython.org.

### You also need the Octal-SPIRAM firmware variant

The ESP32-S3 chip used on the T-Display S3 (an **ESP32-S3R8**) has 8 MB of
**Octal**-SPI PSRAM, not the more common Quad-SPI PSRAM. A firmware build
compiled for Quad PSRAM (or without PSRAM support at all) will not detect
it correctly. Without working PSRAM, the internal ~250 KB of SRAM is not
enough to keep the display (needs a contiguous ~108 KB framebuffer), the
WiFi stack, and TLS/HTTPS connections all active at once — you'll see
`MemoryError` / `ESP_ERR_NO_MEM` errors when initializing the display or
WiFi.

Get the firmware from the `firmware/` folder of the `s3lcd` repository (or
its sibling repos `st7789s3_esp_lcd` / `t-display-s3`), and specifically
pick the **`GENERIC_S3_OCT_16M`** variant (Octal SPIRAM, 16 MB flash) — not
`GENERIC_S3_16M` (that one is Quad SPIRAM and will not work correctly on
this board).

### Flashing

```bash
pip install esptool
esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash
esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 921600 \
  --before default_reset --after hard_reset \
  write_flash -z --flash_mode dio --flash_freq 80m 0x0 firmware.bin
```

Putting the board into flash mode: hold **BOOT**, tap **RST**, release
**BOOT**. Port is typically `/dev/ttyACM0`/`/dev/ttyUSB0` on Linux,
`COMx` on Windows, `/dev/cu.usbmodemXXXX` on macOS.

After flashing, verify in the REPL:
```python
import gc
gc.mem_free()          # should be several million bytes, not ~250000
import os
os.uname()              # should mention "Octal-SPIRAM"
```

## Uploading the project files

```bash
pip install mpremote
mpremote connect /dev/ttyACM0 fs cp boot.py main.py tft_config.py display.py \
  wifi_manager.py config_store.py ntp_clock.py widgets.py webserver.py :
```

`urequests` is not shipped as a separate file — it's already a frozen
module on this firmware build. Verify with `help('modules')` in the REPL
if you're unsure.

## First boot / WiFi setup

1. On first boot (no saved WiFi credentials), the device opens its own
   access point: SSID `MagicMirror-Setup`, password `mirror1234` (both
   shown on the display too).
2. Connect to that WiFi from your phone/laptop, open a browser to the IP
   shown on the display (usually `http://192.168.4.1`).
3. Enter your real WiFi SSID/password, save, restart.
4. After reconnecting, open the web UI at the device's new IP (visible on
   the boot screen, or check your router) to configure every widget:
   location search for weather/air quality, postal-code search for NINA
   warnings, your private iCal URL for the calendar, coin/stock symbols,
   and your DEFCON endpoint URL.

The web UI is always reachable — at `192.168.4.1` in setup-AP mode, or at
the device's regular IP once connected to your WiFi.

## Buttons

The board's two built-in buttons (GPIO0/BOOT and GPIO14) let you page
through widgets manually. Pressing either button switches the display to
manual mode **for the rest of that session** (until the next restart) —
GPIO0 goes back, GPIO14 goes forward. The clock keeps ticking every second
regardless of mode, as long as it's the widget currently shown.

## Turning widgets on/off

The "Widgets" card at the top of the web UI has a checkbox per widget.
Unchecked widgets are skipped both in the automatic rotation and when
paging manually with the buttons. If everything gets disabled by mistake,
the device falls back to showing just the clock so the screen never goes
blank.

## Setting up Google Calendar

1. Google Calendar → Settings → your calendar → "Integrate calendar".
2. Copy the "Secret address in iCal format" (not the public iCal address).
3. Paste it into the "Calendar" card in the web UI, save.

Complex recurring events (RRULE with exceptions) are only considered by
their original start date, not fully expanded — fine for an at-a-glance
wall display, not a substitute for a full calendar app.

## Setting up NINA warnings

Search by postal code if the place-name search doesn't return results —
it tends to be more reliable. Note: city-states (Hamburg, Berlin, Bremen)
have no separate "district" entry in the underlying lookup API since
there's no Kreis level above the city itself; the search falls back to the
municipality code in that case, which is handled automatically.

## Project structure

```
main.py            Entry point: WiFi, webserver task, display loop, buttons
boot.py             Minimal boot init
tft_config.py       Display bus configuration (i80/parallel bus, s3lcd)
display.py          Framebuffer-free drawing wrapper (draws straight into
                     s3lcd's own internal buffer), bitmap + vector text
wifi_manager.py      STA connection with AP fallback
config_store.py      JSON configuration load/save (/config.json on device)
ntp_clock.py          NTP sync + local time incl. EU daylight saving
widgets.py            Data fetching (Open-Meteo, NINA, CoinGecko, Yahoo
                       Finance, EWS, DEFCON, iCal) + drawing routines
webserver.py           uasyncio HTTP server + embedded web UI
```

## Memory & rendering notes

`s3lcd.ESPLCD()` allocates its own internal framebuffer at the full
display size (170×320×2 = 108,800 bytes). `display.py` draws directly
using `ESPLCD`'s built-in methods (`fill`, `rect`, `line`, `circle`,
`text`, `draw` for the vector font, …) instead of keeping a second
Python-side framebuffer.

Most text uses the bitmap fonts frozen into this firmware build
(`vga1_8x8`, `vga1_16x16`, `vga1_bold_16x32`); the clock specifically uses
a Hershey vector font (`romans`) for a smooth, large, non-blocky look at
any size. If your firmware build freezes different module names, check
`help('modules')` in the REPL and adjust the imports at the top of
`display.py`/`widgets.py`.

## Testing locally without hardware

```bash
cd magic-mirror-mini
pip install -r requirements.txt   # if you've split out a dev/test env
```

There's no bundled hardware simulator in this repo — layout and font
choices were tuned iteratively on real hardware over the course of
development. If you want to speed up future layout work, consider writing
a small Pillow-based renderer that mirrors `display.py`'s drawing API.

## Credits

- Display driver: [`s3lcd`](https://github.com/russhughes/s3lcd) by
  russhughes (MIT license)
- Weather/air quality: [Open-Meteo](https://open-meteo.com/)
- Official warnings: [NINA/BBK](https://warnung.bund.de/)
- Location search for warnings: [OpenPLZ API](https://openplzapi.org/)
- Crypto prices: [CoinGecko](https://www.coingecko.com/)
- Stock prices: Yahoo Finance chart endpoint (unofficial)
- Apocalypse Early Warning System: [ews.kylemcdonald.net](https://ews.kylemcdonald.net/)
  by Kyle McDonald

## License

GPL-3.0 — see [LICENSE](LICENSE).
