# Firmware

This folder contains the exact MicroPython firmware binary this project
was built and tested against: **`GENERIC_S3_OCT_16M`** — the Octal-SPIRAM
variant for boards with 16 MB flash, combined with the
[`s3lcd`](https://github.com/russhughes/s3lcd) parallel-bus display driver
(by russhughes) needed for the T-Display S3's i80 display bus.

It's included here as a known-working, ready-to-flash copy so the project
stays reproducible even if the upstream firmware release layout changes.
**Always prefer the original source below if you want the latest version**
— this local copy exists for convenience and archival purposes.

## Original source

- Repository: <https://github.com/russhughes/s3lcd>
- Look inside the `firmware/` folder there for the `GENERIC_S3_OCT_16M`
  variant specifically. Sibling repos by the same author
  (`st7789s3_esp_lcd`, `t-display-s3`) sometimes carry the same or newer
  builds if the main repo's firmware folder has moved on.
- License: MIT (see the `s3lcd` repository for the exact license text)

## Why this specific variant

The T-Display S3 uses an **ESP32-S3R8** chip with **Octal**-SPI PSRAM (not
the more common Quad-SPI PSRAM). A firmware build for Quad PSRAM — or one
without PSRAM support at all — will not detect it correctly, and the
~250 KB of internal SRAM alone is not enough to run the display, WiFi, and
HTTPS connections at the same time (see the main README's firmware
section for details on the `MemoryError`/`ESP_ERR_NO_MEM` symptoms this
causes).

## Flashing

```bash
pip install esptool
esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash
esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 921600 \
  --before default_reset --after hard_reset \
  write_flash -z --flash_mode dio --flash_freq 80m 0x0 firmware.bin
```

See the main [README](../README.md) for how to enter flash mode and how
to verify afterwards that Octal-SPIRAM was detected correctly.
