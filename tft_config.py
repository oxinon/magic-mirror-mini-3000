"""
LilyGO T-Display S3 – 1.9" ST7789, 170x320, angebunden über den
8-Bit-Parallelbus (Intel 8080 / i80), NICHT über SPI.

Diese Datei stammt (leicht angepasst) aus den Beispielen des s3lcd-Treibers
von russhughes: https://github.com/russhughes/s3lcd

Wichtig: Diese Pins sind auf dem T-Display S3 fest verlötet, du musst dort
nichts verkabeln oder anpassen – die Konfiguration passt direkt zum Board.
"""

from machine import Pin, freq
import s3lcd

# Fest verdrahtete Steuer-Pins auf dem T-Display S3
LCD_POWER = Pin(15, Pin.OUT)   # muss high sein, sonst bleibt das Panel aus
RD = Pin(9, Pin.OUT)
BACKLIGHT = Pin(38, Pin.OUT)

WIDTH = 170
HEIGHT = 320

# CPU auf volle Geschwindigkeit, damit das Blitten der Framebuffer flott geht
freq(240_000_000)


def config(rotation=1, options=0):
    """Display initialisieren und ein ESPLCD-Objekt zurückgeben.

    rotation=1 -> Querformat (320x170), Kabel/USB-Anschluss links.
    """
    LCD_POWER.value(1)
    RD.value(1)
    BACKLIGHT.value(1)

    bus = s3lcd.I80_BUS(
        (39, 40, 41, 42, 45, 46, 47, 48),  # Datenleitungen D0..D7
        dc=7,
        wr=8,
        cs=6,
        pclk=20_000_000,
        swap_color_bytes=True,
        reverse_color_bits=False,
    )

    tft = s3lcd.ESPLCD(
        bus,
        WIDTH,
        HEIGHT,
        reset=5,
        rotation=rotation,
        inversion_mode=True,
        color_space=s3lcd.RGB,
        options=options,
    )
    tft.init()
    return tft


def deinit(tft, display_off=False):
    tft.deinit()
    if display_off:
        BACKLIGHT.value(0)
        RD.value(0)
        LCD_POWER.value(0)
