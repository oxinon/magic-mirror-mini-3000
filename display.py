"""
Zeichen-Wrapper um s3lcd/ESPLCD.

Wichtig, nach dem MemoryError-Debugging: s3lcd.ESPLCD() legt SELBST schon
einen internen Framebuffer der vollen Displaygroesse an (170*320*2 Bytes).
Ein zweiter framebuf.FrameBuffer in Python waere doppelt gemoppelt und
sprengt auf einem Board ohne aktives PSRAM den Heap. Wir zeichnen daher
direkt mit den eingebauten Methoden von ESPLCD (fill, rect, line, circle,
text, ...) -- die brauchen keinen zusaetzlichen Puffer.

Fuer Text nutzen wir die auf diesem Firmware-Build eingefrorenen Bitmap-
Fonts (per `help('modules')` bestaetigt: vga1_8x8, vga1_16x16, vga1_16x32,
vga1_bold_16x32, ...). Kein zusaetzlicher Font-Upload noetig.
"""

import framebuf
import s3lcd
import tft_config

import vga1_8x8 as FONT_SMALL
import vga1_16x16 as FONT_MEDIUM
import vga1_bold_16x32 as FONT_LARGE

WIDTH = tft_config.HEIGHT   # 320 (Querformat)
HEIGHT = tft_config.WIDTH   # 170

BLACK = s3lcd.BLACK
WHITE = s3lcd.WHITE
RED = s3lcd.color565(0xFF, 0x55, 0x55)
GREEN = s3lcd.color565(0x7F, 0xAE, 0x7A)
BLUE = s3lcd.BLUE
CYAN = s3lcd.CYAN
YELLOW = s3lcd.YELLOW

# Farbpalette 1:1 aus dem Docker-Magic-Mirror-Projekt uebernommen
# (siehe mirror.css: gedaempftes Messing/Gold als Akzentfarbe statt Neon).
FG = s3lcd.color565(0xEE, 0xF0, 0xF2)         # --mm-fg
FG_DIM = s3lcd.color565(0x8B, 0x8F, 0x96)     # --mm-fg-dim
FG_FAINT = s3lcd.color565(0x52, 0x55, 0x5B)   # --mm-fg-faint
ACCENT = s3lcd.color565(0xC9, 0xA1, 0x5A)     # --mm-accent (Messing/Gold)
ACCENT_DIM = s3lcd.color565(0x7D, 0x67, 0x38) # --mm-accent-dim
UP = s3lcd.color565(0x7F, 0xAE, 0x7A)         # --mm-up
DOWN = s3lcd.color565(0xB9, 0x6A, 0x5A)       # --mm-down
AMBER = s3lcd.color565(0xF5, 0xB9, 0x42)      # --mm-amber
ALERT_RED = s3lcd.color565(0xFF, 0x55, 0x55)  # --mm-red

# Aliase fuer bestehenden Code
GRAY = FG_DIM
DARKGRAY = FG_FAINT

FONTS = {
    "small": FONT_SMALL,
    "medium": FONT_MEDIUM,
    "large": FONT_LARGE,
}


def rgb(r, g, b):
    return s3lcd.color565(r, g, b)


class Display:
    def __init__(self):
        self.tft = tft_config.config(rotation=1)

    # -- low level -----------------------------------------------------
    def clear(self, color=BLACK):
        self.tft.fill(color)

    def show(self):
        self.tft.show()

    def deinit(self, display_off=False):
        """Gibt den Display-Speicher (inkl. des grossen internen Framebuffers)
        wieder frei. Wichtig, bevor speicherhungrige Dinge wie die
        WLAN-Initialisierung laufen -- danach kann die Display wieder per
        Display() neu angelegt werden (kein Hard-Reset noetig)."""
        tft_config.deinit(self.tft, display_off)

    def rect(self, x, y, w, h, color, fill=False):
        if fill:
            self.tft.fill_rect(x, y, w, h, color)
        else:
            self.tft.rect(x, y, w, h, color)

    def hline(self, x, y, w, color):
        self.tft.hline(x, y, w, color)

    def vline(self, x, y, h, color):
        self.tft.vline(x, y, h, color)

    def line(self, x0, y0, x1, y1, color):
        self.tft.line(x0, y0, x1, y1, color)

    def circle_fill(self, cx, cy, r, color):
        self.tft.fill_circle(cx, cy, r, color)

    def pixel(self, x, y, color):
        self.tft.pixel(x, y, color)

    # -- text ------------------------------------------------------------
    def text(self, s, x, y, color=WHITE, size="small", bg=BLACK):
        font = FONTS.get(size, FONT_SMALL)
        self.tft.text(font, s, x, y, color, bg)

    def text_width(self, s, size="small"):
        font = FONTS.get(size, FONT_SMALL)
        w = getattr(font, "WIDTH", 8)
        return w * len(s)

    def text_centered(self, s, cx, y, color=WHITE, size="small", bg=BLACK):
        w = self.text_width(s, size)
        self.text(s, cx - w // 2, y, color, size, bg)

    # -- frei skalierbarer Text (fuer besonders grosse Anzeigen wie die
    #    Uhrzeit) -- nutzt den eingebauten 8x8-Font von framebuf und
    #    skaliert ihn pixelgenau hoch, unabhaengig von den festen
    #    Bitmap-Font-Groessen der Firmware. Dank PSRAM unproblematisch. --
    def text_big(self, s, x, y, color=WHITE, scale=4):
        w = 8 * len(s)
        h = 8
        buf = bytearray(w * h * 2)
        fb = framebuf.FrameBuffer(buf, w, h, framebuf.RGB565)
        fb.fill(0x0000)
        fb.text(s, 0, 0, 0xFFFF)
        for ty in range(h):
            for tx in range(w):
                if fb.pixel(tx, ty):
                    self.tft.fill_rect(x + tx * scale, y + ty * scale, scale, scale, color)

    def text_big_width(self, s, scale=4):
        return 8 * len(s) * scale

    def text_big_centered(self, s, cx, y, color=WHITE, scale=4):
        w = self.text_big_width(s, scale)
        self.text_big(s, cx - w // 2, y, color, scale)

    def draw_vector(self, font, s, x, y, color=WHITE, scale=1.0):
        """Zeichnet Text mit einem Hershey-Vektorfont (Linienzuege statt
        Pixel-Bitmap) -- skaliert glatt, ohne Blockpixel-Optik. x/y sind
        die untere linke Ecke (Baseline)."""
        self.tft.draw(font, s, x, y, color, scale)

    def vector_width(self, font, s, scale=1.0):
        return self.tft.draw_len(font, s, scale)

    def draw_vector_centered(self, font, s, cx, y, color=WHITE, scale=1.0):
        w = self.vector_width(font, s, scale)
        self.draw_vector(font, s, cx - w // 2, y, color, scale)

    def fit_vector_scale(self, font, s, max_width, max_scale=6.0, min_scale=1.0):
        """Groesstmoegliche (Fliesskomma-)Skalierung fuer draw_vector, die
        s noch in max_width Pixel passen laesst."""
        w1 = self.vector_width(font, s, 1.0)
        if w1 <= 0:
            return min_scale
        scale = max_width / w1
        return max(min_scale, min(max_scale, scale))

    def fit_scale(self, s, max_width, max_scale=8):
        """Groesstmoegliche Skalierung fuer text_big, die s noch in
        max_width Pixel passen laesst."""
        scale = max_width // (8 * max(1, len(s)))
        return max(1, min(max_scale, scale))

    # -- kleine Icon-Bausteine (bewusst simpel/geometrisch, keine Bilder
    #    noetig -> funktioniert ohne zusaetzliche Assets auf dem Geraet) --
    def icon_sun(self, cx, cy, r, color=AMBER):
        self.circle_fill(cx, cy, r, color)
        import math
        for i in range(8):
            a = i * (2 * math.pi / 8)
            x0 = int(cx + math.cos(a) * (r + 3))
            y0 = int(cy + math.sin(a) * (r + 3))
            x1 = int(cx + math.cos(a) * (r + 7))
            y1 = int(cy + math.sin(a) * (r + 7))
            self.line(x0, y0, x1, y1, color)

    def icon_cloud(self, cx, cy, r, color=GRAY):
        self.circle_fill(cx - r // 2, cy, int(r * 0.7), color)
        self.circle_fill(cx + r // 2, cy, int(r * 0.7), color)
        self.circle_fill(cx, cy - r // 3, int(r * 0.8), color)
        self.rect(cx - r, cy, 2 * r, r // 2 + 2, color, fill=True)

    def icon_rain(self, cx, cy, r, color=BLUE):
        self.icon_cloud(cx, cy - 6, r, GRAY)
        for dx in (-8, 0, 8):
            self.line(cx + dx, cy + r, cx + dx - 3, cy + r + 10, color)

    def icon_snow(self, cx, cy, r, color=WHITE):
        self.icon_cloud(cx, cy - 6, r, GRAY)
        for dx in (-8, 0, 8):
            self.circle_fill(cx + dx, cy + r + 6, 1, color)

    def icon_storm(self, cx, cy, r, color=YELLOW):
        self.icon_cloud(cx, cy - 6, r, DARKGRAY)
        self.line(cx, cy + r, cx - 6, cy + r + 8, color)
        self.line(cx - 6, cy + r + 8, cx + 2, cy + r + 8, color)
        self.line(cx + 2, cy + r + 8, cx - 4, cy + r + 18, color)

    def icon_fog(self, cx, cy, r, color=GRAY):
        for dy in (-6, 0, 6, 12):
            self.hline(cx - r, cy + dy, 2 * r, color)
