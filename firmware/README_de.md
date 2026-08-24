# Firmware

Dieser Ordner enthält genau die MicroPython-Firmware-Datei, gegen die
dieses Projekt gebaut und getestet wurde: **`GENERIC_S3_OCT_16M`** – die
Octal-SPIRAM-Variante für Boards mit 16 MB Flash, kombiniert mit dem
Parallelbus-Display-Treiber [`s3lcd`](https://github.com/russhughes/s3lcd)
(von russhughes), der für den i80-Display-Bus des T-Display S3 nötig ist.

Sie liegt hier als bekannt funktionierende, sofort flashbare Kopie bei,
damit das Projekt reproduzierbar bleibt, auch falls sich die Struktur der
Original-Releases mal ändert. **Bei Bedarf nach der neuesten Version immer
zuerst die Originalquelle unten bevorzugen** – diese lokale Kopie dient
der Bequemlichkeit und Archivierung.

## Originalquelle

- Repository: <https://github.com/russhughes/s3lcd>
- Dort im `firmware/`-Ordner gezielt nach der Variante
  `GENERIC_S3_OCT_16M` schauen. Die Schwester-Repos desselben Autors
  (`st7789s3_esp_lcd`, `t-display-s3`) führen teilweise dieselben oder
  neuere Builds, falls sich der Firmware-Ordner im Haupt-Repo verschoben
  hat.
- Lizenz: MIT (genauen Lizenztext siehe `s3lcd`-Repository)

## Warum genau diese Variante

Das T-Display S3 nutzt einen **ESP32-S3R8**-Chip mit **Octal**-SPI-PSRAM
(nicht das gewöhnlichere Quad-SPI-PSRAM). Eine für Quad-PSRAM gebaute
Firmware – oder eine ganz ohne PSRAM-Unterstützung – erkennt es nicht
richtig, und die ~250 KB internes SRAM allein reichen nicht, um Display,
WLAN und HTTPS-Verbindungen gleichzeitig laufen zu lassen (Details zu den
dadurch verursachten `MemoryError`/`ESP_ERR_NO_MEM`-Symptomen siehe
Firmware-Abschnitt der Haupt-README).

## Flashen

```bash
pip install esptool
esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash
esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 921600 \
  --before default_reset --after hard_reset \
  write_flash -z --flash_mode dio --flash_freq 80m 0x0 firmware.bin
```

Wie man das Board in den Flash-Modus versetzt und danach prüft, ob
Octal-SPIRAM korrekt erkannt wurde, steht in der Haupt-[README](../README_de.md).
