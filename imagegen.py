"""Drawcustom rendering engine for Wolink ESL e-paper labels.

Renders a list of element dicts into a PIL Image. The public entry point
``render_drawcustom`` handles Jinja template resolution and runs Pillow
work in an executor. The internal ``_render_sync`` is a pure-Pillow
function with no HA dependencies, easily testable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Path to bundled fonts inside the integration
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# ─── Color mapping ───────────────────────────────────────────────────

_NAMED_COLORS: dict[str, tuple[int, int, int, int]] = {
    "black": (0, 0, 0, 255),
    "white": (255, 255, 255, 255),
    "red": (255, 0, 0, 255),
    "yellow": (255, 255, 0, 255),
    "accent": (255, 0, 0, 255),  # OEPL compat — maps to red
}

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _resolve_color(name: str) -> tuple[int, int, int, int]:
    """Resolve a color name or hex string to an RGBA tuple."""
    if not isinstance(name, str):
        _LOGGER.warning("Invalid color value %r, falling back to black", name)
        return (0, 0, 0, 255)

    lower = name.strip().lower()
    if lower in _NAMED_COLORS:
        return _NAMED_COLORS[lower]

    m = _HEX_RE.match(name.strip())
    if m:
        hex_str = m.group(1)
        if len(hex_str) == 6:
            r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
            return (r, g, b, 255)
        else:
            r, g, b, a = (
                int(hex_str[0:2], 16),
                int(hex_str[2:4], 16),
                int(hex_str[4:6], 16),
                int(hex_str[6:8], 16),
            )
            return (r, g, b, a)

    _LOGGER.warning("Unknown color %r, falling back to black", name)
    return (0, 0, 0, 255)


# ─── Font loading ────────────────────────────────────────────────────

def _load_font(name: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font by name+size. Falls back to bundled Roboto Medium."""
    if name:
        # Try integration fonts dir first
        local_path = os.path.join(_FONTS_DIR, name)
        if os.path.isfile(local_path):
            try:
                return ImageFont.truetype(local_path, size)
            except Exception:
                pass
        # Try system font
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            _LOGGER.warning("Font %r not found, using default", name)

    # Default: bundled Roboto Medium → DejaVuSans → Pillow built-in
    for fallback in ("rbm.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(os.path.join(_FONTS_DIR, fallback), size)
        except Exception:
            pass
    return ImageFont.load_default(size=size)


def _read_os2_metrics(font_path: str) -> tuple[int, int, int, int, int] | None:
    """Read UPM, sTypoAscender, sTypoDescender, fsSelection, usWinAscent from a TTF/OTF file.

    Returns ``(upm, typo_asc, typo_desc, fs_selection, win_ascent)`` or *None* on failure.
    Parses just the ``head`` and ``OS/2`` table headers — no external deps.
    """
    import struct

    try:
        with open(font_path, "rb") as f:
            data = f.read()
    except Exception:
        return None

    if len(data) < 12:
        return None

    num_tables = struct.unpack_from(">H", data, 4)[0]
    tables: dict[str, tuple[int, int]] = {}
    for i in range(num_tables):
        off = 12 + i * 16
        tag = data[off : off + 4].decode("ascii", errors="replace")
        tbl_offset = struct.unpack_from(">I", data, off + 8)[0]
        tbl_length = struct.unpack_from(">I", data, off + 12)[0]
        tables[tag] = (tbl_offset, tbl_length)

    if "head" not in tables or "OS/2" not in tables:
        return None

    head_off = tables["head"][0]
    upm = struct.unpack_from(">H", data, head_off + 18)[0]

    os2_off = tables["OS/2"][0]
    fs_selection = struct.unpack_from(">H", data, os2_off + 62)[0]
    typo_asc = struct.unpack_from(">h", data, os2_off + 68)[0]
    typo_desc = struct.unpack_from(">h", data, os2_off + 70)[0]
    win_ascent = struct.unpack_from(">H", data, os2_off + 74)[0]

    return (upm, typo_asc, typo_desc, fs_selection, win_ascent)


_em_offset_cache: dict[str, int] = {}


def _cap_top_offset(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    """Offset from PIL ascender to CSS em-box top for text-before-edge matching.

    SVG ``dominant-baseline="text-before-edge"`` places the **em-box top** at y.
    PIL ``anchor="la"`` places the **ascender** at y.  The ascender may extend
    above the em-box top, so we compute the gap from the font's OS/2 metrics
    (same tables browsers use for text layout).

    Content-independent: the result depends only on the font and size.
    """
    try:
        size = font.size
        path = font.path if hasattr(font, "path") else None
        cache_key = f"{path}:{size}" if isinstance(path, str) else ""
        if cache_key and cache_key in _em_offset_cache:
            return _em_offset_cache[cache_key]

        ascent = font.getmetrics()[0]
        offset = 0

        if isinstance(path, str):
            metrics = _read_os2_metrics(path)
            if metrics is not None:
                upm, typo_asc, typo_desc, fs_sel, win_ascent = metrics
                use_typo = bool(fs_sel & (1 << 7))
                if use_typo and upm > 0:
                    em_ascent = round(typo_asc / upm * size)
                elif upm > 0:
                    em_ascent = round(win_ascent / upm * size)
                else:
                    em_ascent = ascent
                offset = max(0, ascent - em_ascent)

        if cache_key:
            _em_offset_cache[cache_key] = offset
        return offset
    except Exception:
        return 0


# ─── MDI icon codepoint lookup ───────────────────────────────────────

_MDI_CODEPOINTS: dict[str, int] = {
    "home": 0xF02DC,
    "thermometer": 0xF050F,
    "water": 0xF058C,
    "lightbulb": 0xF0335,
    "weather-sunny": 0xF0599,
    "weather-cloudy": 0xF0590,
    "wifi": 0xF05A9,
    "battery": 0xF007A,
    "bell": 0xF009A,
    "eye": 0xF0208,
    "trash-can": 0xF0A79,
    "calendar": 0xF00ED,
    "clock": 0xF0954,
    "check": 0xF012C,
    "close": 0xF0156,
    "alert": 0xF0026,
    "information": 0xF02FC,
    "cog": 0xF0493,
    "power": 0xF0425,
    "refresh": 0xF0450,
}

_mdi_meta: dict[str, str] | None = None


def _load_mdi_meta() -> dict[str, str]:
    """Load MDI metadata JSON and build a name/alias → codepoint_hex mapping.

    Loaded lazily on first icon render, then cached for the process lifetime.
    """
    global _mdi_meta
    if _mdi_meta is not None:
        return _mdi_meta

    meta_path = os.path.join(_FONTS_DIR, "materialdesignicons-webfont_meta.json")
    try:
        with open(meta_path) as f:
            icons = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as err:
        _LOGGER.warning("MDI metadata not available (%s), falling back to hardcoded icons", err)
        _mdi_meta = {}
        return _mdi_meta

    mapping: dict[str, str] = {}
    for icon in icons:
        cp = icon["codepoint"]
        mapping[icon["name"]] = cp
        for alias in icon.get("aliases", []):
            mapping[alias] = cp
    _mdi_meta = mapping
    return _mdi_meta


def _mdi_name_to_char(name: str) -> str | None:
    """Map an MDI icon name (with or without 'mdi:' prefix) to its Unicode character."""
    # Strip mdi: prefix if present
    name = name.removeprefix("mdi:")

    # Try metadata JSON first
    meta = _load_mdi_meta()
    cp_hex = meta.get(name)
    if cp_hex is not None:
        return chr(int(cp_hex, 16))

    # Fall back to hardcoded dict
    codepoint = _MDI_CODEPOINTS.get(name)
    if codepoint is not None:
        return chr(codepoint)

    _LOGGER.warning("Unknown MDI icon %r, using placeholder", name)
    return None


# ─── Element handlers ────────────────────────────────────────────────

def _draw_text(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a single-line text element."""
    value = str(el.get("value", ""))
    x = int(el.get("x", 0))
    y = int(el.get("y", 0))
    size = int(el.get("size", 20))
    font_name = el.get("font")
    color = _resolve_color(el.get("color", "black"))
    anchor = el.get("anchor")

    font = _load_font(font_name, size)
    kwargs: dict[str, Any] = {"fill": color}
    if anchor:
        kwargs["anchor"] = anchor
        draw.text((x, y), value, font=font, **kwargs)
    else:
        # Align cap-top to y (matches SVG text-before-edge), content-independent
        kwargs["anchor"] = "la"
        draw.text((x, y - _cap_top_offset(font)), value, font=font, **kwargs)


def _draw_line(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a line element."""
    x_start = int(el.get("x_start", 0))
    y_start = int(el.get("y_start", 0))
    x_end = int(el.get("x_end", 0))
    y_end = int(el.get("y_end", 0))
    fill = _resolve_color(el.get("fill", "black"))
    width = int(el.get("width", 1))

    draw.line([(x_start, y_start), (x_end, y_end)], fill=fill, width=width)


def _draw_rectangle(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a rectangle element."""
    x_start = int(el.get("x_start", 0))
    y_start = int(el.get("y_start", 0))
    x_end = int(el.get("x_end", 0))
    y_end = int(el.get("y_end", 0))

    fill = _resolve_color(el["fill"]) if "fill" in el else None
    outline = _resolve_color(el["outline"]) if "outline" in el else None
    width = int(el.get("width", 1))

    draw.rectangle(
        [(x_start, y_start), (x_end, y_end)],
        fill=fill,
        outline=outline,
        width=width,
    )


def _draw_icon(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw an MDI icon element."""
    value = str(el.get("value", ""))
    x = int(el.get("x", 0))
    y = int(el.get("y", 0))
    size = int(el.get("size", 24))
    color = _resolve_color(el.get("color", "black"))

    # Strip "mdi:" prefix if present
    icon_name = value.removeprefix("mdi:")

    mdi_font_path = os.path.join(_FONTS_DIR, "materialdesignicons-webfont.ttf")
    if not os.path.isfile(mdi_font_path):
        _LOGGER.warning(
            "MDI font not found at %s — rendering placeholder for icon %r",
            mdi_font_path,
            value,
        )
        _draw_placeholder(draw, x, y, size, "?")
        return

    char = _mdi_name_to_char(icon_name)
    if char is None:
        _draw_placeholder(draw, x, y, size, "?")
        return

    try:
        font = ImageFont.truetype(mdi_font_path, size)
    except Exception:
        _LOGGER.warning("Failed to load MDI font, rendering placeholder")
        _draw_placeholder(draw, x, y, size, "?")
        return

    draw.text((x, y - _cap_top_offset(font)), char, font=font, fill=color, anchor="la")


def _draw_placeholder(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, text: str = "?") -> None:
    """Draw a placeholder rectangle with text for missing icons/images."""
    draw.rectangle(
        [(x, y), (x + size, y + size)],
        outline=(128, 128, 128, 255),
        width=1,
    )
    try:
        small_font = ImageFont.load_default(size=max(size // 2, 10))
    except TypeError:
        small_font = ImageFont.load_default()
    draw.text((x + size // 4, y + size // 4), text, font=small_font, fill=(128, 128, 128, 255))


def _draw_dlimg(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any], downloaded_images: dict[str, Image.Image] | None = None) -> None:
    """Draw a downloaded/local image element."""
    from PIL import ImageEnhance

    url = str(el.get("url", ""))
    x = int(el.get("x", 0))
    y = int(el.get("y", 0))
    xsize = int(el.get("xsize", el.get("width", 0)))
    ysize = int(el.get("ysize", el.get("height", 0)))

    source_img = None
    if downloaded_images and url in downloaded_images:
        source_img = downloaded_images[url]
    elif url.startswith("/"):
        # Local file path
        try:
            source_img = Image.open(url)
        except Exception as err:
            _LOGGER.warning("Failed to load local image %r: %s", url, err)
    else:
        _LOGGER.warning("Image for url %r not available", url)

    if source_img is None:
        _draw_placeholder(draw, x, y, max(xsize, ysize, 24), "IMG")
        return

    # Crop before resize (crop region in source pixel coordinates)
    crop = el.get("crop")
    if crop and len(crop) == 4:
        cx, cy, cw, ch = (int(v) for v in crop)
        source_img = source_img.crop((cx, cy, cx + cw, cy + ch))

    if xsize > 0 and ysize > 0:
        source_img = source_img.resize((xsize, ysize), Image.Resampling.LANCZOS)

    # Image adjustments (1.0 = no change)
    saturation = float(el.get("saturation", 1.0))
    if saturation != 1.0:
        source_img = ImageEnhance.Color(source_img.convert("RGB")).enhance(saturation)

    contrast = float(el.get("contrast", 1.0))
    if contrast != 1.0:
        source_img = ImageEnhance.Contrast(source_img.convert("RGB")).enhance(contrast)

    # Per-element rotation
    rotate_deg = int(el.get("rotate", 0))
    if rotate_deg:
        source_img = source_img.rotate(-rotate_deg, expand=True)

    # Convert to RGBA for proper pasting
    if source_img.mode != "RGBA":
        source_img = source_img.convert("RGBA")

    img.paste(source_img, (x, y), source_img)


def _draw_ellipse(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw an ellipse element."""
    x_start = int(el.get("x_start", 0))
    y_start = int(el.get("y_start", 0))
    x_end = int(el.get("x_end", 0))
    y_end = int(el.get("y_end", 0))

    fill = _resolve_color(el["fill"]) if "fill" in el else None
    outline = _resolve_color(el["outline"]) if "outline" in el else None
    width = int(el.get("width", 1))

    draw.ellipse(
        [(x_start, y_start), (x_end, y_end)],
        fill=fill,
        outline=outline,
        width=width,
    )


# ─── Tier 2 element handlers ─────────────────────────────────────────

def _draw_multiline(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw multi-line text, split by a delimiter."""
    value = str(el.get("value", ""))
    x = int(el.get("x", 0))
    y = int(el.get("y", 0))
    size = int(el.get("size", 20))
    font_name = el.get("font")
    color = _resolve_color(el.get("color", "black"))
    anchor = el.get("anchor")
    delimiter = el.get("delimiter", "\n")
    max_width = el.get("max_width")

    font = _load_font(font_name, size)
    line_spacing = int(size * 1.2)

    lines = value.split(delimiter)

    # If max_width is set, wrap lines
    if max_width is not None:
        max_width = int(max_width)
        wrapped = []
        for line in lines:
            if not line:
                wrapped.append(line)
                continue
            words = line.split(" ")
            current = words[0]
            for word in words[1:]:
                test = current + " " + word
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] > max_width:
                    wrapped.append(current)
                    current = word
                else:
                    current = test
            wrapped.append(current)
        lines = wrapped

    kwargs: dict[str, Any] = {"fill": color}
    if anchor:
        kwargs["anchor"] = anchor
        for i, line in enumerate(lines):
            draw.text((x, y + i * line_spacing), line, font=font, **kwargs)
    else:
        # Align cap-top to y (matches SVG text-before-edge), content-independent
        kwargs["anchor"] = "la"
        y_adj = y - _cap_top_offset(font)
        for i, line in enumerate(lines):
            draw.text((x, y_adj + i * line_spacing), line, font=font, **kwargs)


def _draw_circle(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a circle element using ellipse with bounding box."""
    cx = int(el.get("x", 0))
    cy = int(el.get("y", 0))
    r = int(el.get("radius", el.get("r", 10)))

    fill = _resolve_color(el["fill"]) if "fill" in el else None
    outline = _resolve_color(el["outline"]) if "outline" in el else None
    width = int(el.get("width", 1))

    draw.ellipse(
        [(cx - r, cy - r), (cx + r, cy + r)],
        fill=fill,
        outline=outline,
        width=width,
    )


def _draw_qrcode(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a QR code element."""
    try:
        import qrcode as qr_lib
    except ImportError:
        _LOGGER.warning("qrcode library not installed — rendering placeholder for QR code")
        x, y = int(el.get("x", 0)), int(el.get("y", 0))
        size = max(int(el.get("xsize", 50)), int(el.get("ysize", 50)))
        _draw_placeholder(draw, x, y, size, "QR")
        return

    value = str(el.get("value", el.get("data", "")))
    x = int(el.get("x", 0))
    y = int(el.get("y", 0))
    box_size = int(el.get("boxsize", el.get("box_size", 1)))
    border = int(el.get("border", 0))
    color_dark = el.get("color_dark", el.get("color", "black"))
    color_light = el.get("color_light", el.get("bgcolor", "white"))

    qr = qr_lib.QRCode(box_size=box_size, border=border)
    qr.add_data(value)
    qr.make(fit=True)
    qr_img = qr.make_image(
        fill_color=_resolve_color(color_dark)[:3],
        back_color=_resolve_color(color_light)[:3],
    ).convert("RGBA")

    # Resize only if explicit xsize/ysize given
    xsize = el.get("xsize", el.get("size"))
    ysize = el.get("ysize", el.get("size"))
    if xsize is not None or ysize is not None:
        w = int(xsize) if xsize is not None else qr_img.width
        h = int(ysize) if ysize is not None else qr_img.height
        qr_img = qr_img.resize((w, h), Image.Resampling.NEAREST)

    img.paste(qr_img, (x, y), qr_img)


def _draw_barcode(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a barcode element."""
    try:
        import barcode as barcode_lib
        from barcode.writer import ImageWriter
    except ImportError:
        _LOGGER.warning("python-barcode library not installed — rendering placeholder for barcode")
        x, y = int(el.get("x", 0)), int(el.get("y", 0))
        size = max(int(el.get("xsize", 50)), int(el.get("ysize", 50)))
        _draw_placeholder(draw, x, y, size, "BAR")
        return

    import io as _io

    value = str(el.get("value", el.get("data", "")))
    x = int(el.get("x", 0))
    y = int(el.get("y", 0))
    xsize = int(el.get("xsize", 200))
    ysize = int(el.get("ysize", 80))
    barcode_type = el.get("code", el.get("type_name", el.get("barcode_type", "code128")))

    try:
        bc_class = barcode_lib.get_barcode_class(barcode_type)
        bc = bc_class(value, writer=ImageWriter())
        buf = _io.BytesIO()
        bc.write(buf)
        buf.seek(0)
        bc_img = Image.open(buf).convert("RGBA")
        bc_img = bc_img.resize((xsize, ysize), Image.Resampling.LANCZOS)
        img.paste(bc_img, (x, y), bc_img)
    except Exception as err:
        _LOGGER.warning("Failed to render barcode: %s", err)
        _draw_placeholder(draw, x, y, max(xsize, ysize, 24), "BAR")


# ─── Tier 3 element handlers ─────────────────────────────────────────

def _draw_progress_bar(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a progress bar element."""
    x_start = int(el.get("x_start", 0))
    y_start = int(el.get("y_start", 0))
    x_end = int(el.get("x_end", 100))
    y_end = int(el.get("y_end", 20))
    progress = float(el.get("progress", 0.0))
    if progress > 1.0:
        progress = progress / 100.0
    progress = max(0.0, min(1.0, progress))
    fill = _resolve_color(el.get("fill", "black"))
    bg = _resolve_color(el.get("background", "white"))
    outline = _resolve_color(el.get("outline", "black"))
    direction = el.get("direction", "right")

    # Draw background rect
    draw.rectangle([(x_start, y_start), (x_end, y_end)], fill=bg, outline=outline)

    # Draw filled portion
    if direction == "up":
        bar_height = int((y_end - y_start) * progress)
        if bar_height > 0:
            draw.rectangle(
                [(x_start + 1, y_end - bar_height), (x_end - 1, y_end - 1)],
                fill=fill,
            )
    else:  # "right" (default)
        bar_width = int((x_end - x_start) * progress)
        if bar_width > 0:
            draw.rectangle(
                [(x_start + 1, y_start + 1), (x_start + bar_width, y_end - 1)],
                fill=fill,
            )


def _draw_diagram(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a simple vertical bar chart."""
    x_start = int(el.get("x_start", 0))
    y_start = int(el.get("y_start", 0))
    x_end = int(el.get("x_end", 100))
    y_end = int(el.get("y_end", 100))
    data = el.get("data", [])
    fill = _resolve_color(el.get("fill", "black"))
    outline = _resolve_color(el.get("outline", "black")) if "outline" in el else None

    if not data:
        return

    chart_w = x_end - x_start
    chart_h = y_end - y_start
    max_val = max(data) if max(data) > 0 else 1
    bar_w = chart_w // len(data)

    for i, val in enumerate(data):
        bar_h = int((val / max_val) * chart_h)
        bx = x_start + i * bar_w
        by = y_end - bar_h

        draw.rectangle(
            [(bx, by), (bx + bar_w - 1, y_end)],
            fill=fill,
            outline=outline,
        )


def _draw_rectangle_pattern(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a grid pattern of rectangles."""
    x_start = int(el.get("x_start", 0))
    y_start = int(el.get("y_start", 0))
    x_size = int(el.get("x_size", 10))
    y_size = int(el.get("y_size", 10))
    x_repeat = int(el.get("x_repeat", 1))
    y_repeat = int(el.get("y_repeat", 1))
    x_offset = int(el.get("x_offset", 0))
    y_offset = int(el.get("y_offset", 0))
    radius = int(el.get("radius", 0))

    fill = _resolve_color(el["fill"]) if "fill" in el else None
    outline = _resolve_color(el["outline"]) if "outline" in el else None
    width = int(el.get("width", 1))

    for row in range(y_repeat):
        for col in range(x_repeat):
            rx = x_start + col * (x_size + x_offset)
            ry = y_start + row * (y_size + y_offset)
            coords = [(rx, ry), (rx + x_size, ry + y_size)]
            if radius > 0:
                draw.rounded_rectangle(coords, radius=radius, fill=fill, outline=outline, width=width)
            else:
                draw.rectangle(coords, fill=fill, outline=outline, width=width)


def _draw_plot(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw a line chart from pre-fetched entity history data."""
    x_start = int(el.get("x_start", 0))
    y_start = int(el.get("y_start", 0))
    x_end = int(el.get("x_end", 100))
    y_end = int(el.get("y_end", 100))
    line_width = int(el.get("size", 1))

    plot_data = el.get("_plot_data", {})
    series_list = el.get("data", [])

    if not plot_data or not series_list:
        # Placeholder outline rectangle
        draw.rectangle([(x_start, y_start), (x_end, y_end)], outline=(128, 128, 128, 255), width=1)
        return

    for series in series_list:
        entity_id = series.get("entity", "")
        color = _resolve_color(series.get("color", "black"))
        points = plot_data.get(entity_id, [])
        if len(points) < 2:
            continue

        timestamps = [p[0] for p in points]
        values = [p[1] for p in points]

        t_min, t_max = min(timestamps), max(timestamps)
        if t_max == t_min:
            t_max = t_min + 1

        # Y-axis range
        low = el.get("low")
        high = el.get("high")
        if low is not None and high is not None:
            v_min, v_max = float(low), float(high)
        else:
            v_min, v_max = min(values), max(values)
            padding = (v_max - v_min) * 0.1 if v_max != v_min else 1.0
            v_min -= padding
            v_max += padding

        # Map to pixel coordinates
        px_points = []
        for t, v in points:
            px_x = x_start + (t - t_min) / (t_max - t_min) * (x_end - x_start)
            px_y = y_end - (v - v_min) / (v_max - v_min) * (y_end - y_start)
            px_points.append((px_x, px_y))

        # Draw line segments
        for i in range(len(px_points) - 1):
            draw.line([px_points[i], px_points[i + 1]], fill=color, width=line_width)


# ─── Element dispatcher ──────────────────────────────────────────────

def _draw_arc(draw: ImageDraw.ImageDraw, img: Image.Image, el: dict[str, Any]) -> None:
    """Draw an arc or pie slice element."""
    cx = int(el.get("x", 0))
    cy = int(el.get("y", 0))
    radius = int(el.get("radius", 10))
    start = float(el.get("start_angle", 0))
    end = float(el.get("end_angle", 90))

    fill = _resolve_color(el["fill"]) if "fill" in el else None
    outline = _resolve_color(el.get("outline", "black")) if "outline" in el or "fill" not in el else None
    width = int(el.get("width", 1))

    bbox = [(cx - radius, cy - radius), (cx + radius, cy + radius)]

    if fill:
        draw.pieslice(bbox, start=start, end=end, fill=fill, outline=outline, width=width)
    else:
        draw.arc(bbox, start=start, end=end, fill=outline, width=width)


_ELEMENT_HANDLERS: dict[str, Any] = {
    "text": _draw_text,
    "line": _draw_line,
    "rectangle": _draw_rectangle,
    "icon": _draw_icon,
    "ellipse": _draw_ellipse,
    "dlimg": _draw_dlimg,
    "multiline": _draw_multiline,
    "circle": _draw_circle,
    "qrcode": _draw_qrcode,
    "barcode": _draw_barcode,
    "progress_bar": _draw_progress_bar,
    "diagram": _draw_diagram,
    "rectangle_pattern": _draw_rectangle_pattern,
    "plot": _draw_plot,
    "arc": _draw_arc,
}


# ─── Dither mask painting ────────────────────────────────────────────

def _paint_mask(mask_draw: ImageDraw.ImageDraw, element: dict[str, Any], mask_val: int) -> None:
    """Paint the element's footprint onto the dither mask."""
    el_type = element.get("type")

    if el_type in ("rectangle", "progress_bar", "diagram", "rectangle_pattern"):
        x0 = int(element.get("x_start", 0))
        y0 = int(element.get("y_start", 0))
        x1 = int(element.get("x_end", 0))
        y1 = int(element.get("y_end", 0))
        mask_draw.rectangle([(x0, y0), (x1, y1)], fill=mask_val)

    elif el_type == "ellipse":
        x0 = int(element.get("x_start", 0))
        y0 = int(element.get("y_start", 0))
        x1 = int(element.get("x_end", 0))
        y1 = int(element.get("y_end", 0))
        mask_draw.ellipse([(x0, y0), (x1, y1)], fill=mask_val)

    elif el_type == "circle":
        cx = int(element.get("x", 0))
        cy = int(element.get("y", 0))
        r = int(element.get("radius", element.get("r", 10)))
        mask_draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=mask_val)

    elif el_type == "arc":
        cx = int(element.get("x", 0))
        cy = int(element.get("y", 0))
        r = int(element.get("radius", 10))
        start = float(element.get("start_angle", 0))
        end = float(element.get("end_angle", 90))
        bbox = [(cx - r, cy - r), (cx + r, cy + r)]
        if "fill" in element:
            mask_draw.pieslice(bbox, start=start, end=end, fill=mask_val)
        else:
            mask_draw.arc(bbox, start=start, end=end, fill=mask_val,
                          width=int(element.get("width", 1)))

    elif el_type == "line":
        x0 = int(element.get("x_start", 0))
        y0 = int(element.get("y_start", 0))
        x1 = int(element.get("x_end", 0))
        y1 = int(element.get("y_end", 0))
        w = int(element.get("width", 1))
        mask_draw.line([(x0, y0), (x1, y1)], fill=mask_val, width=w)

    elif el_type in ("text", "icon"):
        x = int(element.get("x", 0))
        y = int(element.get("y", 0))
        s = int(element.get("size", 20 if el_type == "text" else 24))
        mask_draw.rectangle([(x, y), (x + s, y + s)], fill=mask_val)

    elif el_type == "multiline":
        x = int(element.get("x", 0))
        y = int(element.get("y", 0))
        s = int(element.get("size", 20))
        value = str(element.get("value", ""))
        delimiter = element.get("delimiter", "\n")
        n_lines = max(len(value.split(delimiter)), 1)
        h = int(s * 1.2 * n_lines)
        max_w = element.get("max_width")
        w = int(max_w) if max_w is not None else max(s * len(value) // max(n_lines, 1), s)
        mask_draw.rectangle([(x, y), (x + w, y + h)], fill=mask_val)

    elif el_type in ("dlimg", "qrcode", "barcode"):
        x = int(element.get("x", 0))
        y = int(element.get("y", 0))
        w = int(element.get("xsize", element.get("size", 48)))
        h = int(element.get("ysize", element.get("size", 48)))
        mask_draw.rectangle([(x, y), (x + w, y + h)], fill=mask_val)

    elif el_type == "plot":
        x0 = int(element.get("x_start", 0))
        y0 = int(element.get("y_start", 0))
        x1 = int(element.get("x_end", 100))
        y1 = int(element.get("y_end", 100))
        mask_draw.rectangle([(x0, y0), (x1, y1)], fill=mask_val)


# ─── Sync rendering core ─────────────────────────────────────────────

def _render_sync(
    payload: list[dict[str, Any]],
    width: int,
    height: int,
    background: str = "white",
    rotate: int = 0,
    downloaded_images: dict[str, Image.Image] | None = None,
    global_dither: str = "floyd-steinberg",
) -> tuple[Image.Image, Image.Image]:
    """Pure-Pillow rendering — no HA dependencies. Easily testable.

    Returns (canvas_rgb, dither_mask) where dither_mask is an L-mode image.
    Each pixel value is a dither algorithm index (0=none, 1=floyd-steinberg,
    2=atkinson, 3=stucki). Returns None as mask when no element has a
    per-element dither override.
    """
    from .wolink import _DITHER_INDEX

    bg_color = _resolve_color(background)
    canvas = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(canvas)

    # Build dither mask: background inherits global setting
    bg_mask_val = _DITHER_INDEX.get(global_dither, 0)
    mask = Image.new("L", (width, height), bg_mask_val)
    mask_draw = ImageDraw.Draw(mask)

    has_per_element_dither = False

    for element in payload:
        el_type = element.get("type")
        handler = _ELEMENT_HANDLERS.get(el_type)
        if handler is None:
            _LOGGER.warning("Unknown element type %r, skipping", el_type)
            continue

        try:
            if el_type == "dlimg":
                handler(draw, canvas, element, downloaded_images)
            else:
                handler(draw, canvas, element)
        except Exception:
            _LOGGER.exception("Error rendering element type %r", el_type)
            continue

        # Stamp element footprint onto dither mask
        el_dither = element.get("dither")
        if el_dither is not None:
            has_per_element_dither = True
            # Normalize legacy boolean values
            if el_dither is True:
                el_dither = "floyd-steinberg"
            elif el_dither is False:
                el_dither = "none"
            mask_val = _DITHER_INDEX.get(el_dither, bg_mask_val)
        else:
            mask_val = bg_mask_val

        _paint_mask(mask_draw, element, mask_val)

    if rotate:
        canvas = canvas.rotate(rotate, expand=True)
        mask = mask.rotate(rotate, expand=True)

    # Only return the mask if per-element overrides exist (optimization)
    return canvas.convert("RGB"), mask if has_per_element_dither else None


# ─── Async entry point ───────────────────────────────────────────────

async def _resolve_templates(hass: HomeAssistant, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Walk payload recursively, rendering Jinja templates in string values."""
    from homeassistant.helpers.template import Template

    def _resolve_value(value: Any) -> Any:
        if isinstance(value, str) and "{{" in value:
            try:
                tpl = Template(value, hass)
                return tpl.async_render()
            except Exception as err:
                _LOGGER.warning("Template rendering failed for %r: %s", value, err)
                return value
        if isinstance(value, dict):
            return {k: _resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_resolve_value(item) for item in value]
        return value

    return [_resolve_value(el) for el in payload]


async def _download_images(hass: HomeAssistant, payload: list[dict[str, Any]]) -> dict[str, Image.Image]:
    """Pre-download all dlimg URLs that need HTTP fetching."""
    import io as _io

    downloaded: dict[str, Image.Image] = {}
    urls = [
        el.get("url", "")
        for el in payload
        if el.get("type") == "dlimg" and str(el.get("url", "")).startswith(("http://", "https://"))
    ]
    if not urls:
        return downloaded

    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    for url in urls:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    downloaded[url] = Image.open(_io.BytesIO(data))
                else:
                    _LOGGER.warning("Failed to download image %r: HTTP %s", url, resp.status)
        except Exception as err:
            _LOGGER.warning("Failed to download image %r: %s", url, err)

    return downloaded


async def _prefetch_plot_data(hass: HomeAssistant, payload: list[dict[str, Any]]) -> None:
    """Pre-fetch recorder history for plot elements and inject _plot_data."""
    from datetime import timedelta

    for el in payload:
        if el.get("type") != "plot":
            continue
        series_list = el.get("data", [])
        entity_ids = [s.get("entity", "") for s in series_list if s.get("entity")]
        if not entity_ids:
            el["_plot_data"] = {}
            continue

        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
            from homeassistant.util.dt import utcnow

            start_time = utcnow() - timedelta(seconds=el.get("duration", 86400))
            instance = get_instance(hass)
            states = await instance.async_add_executor_job(
                get_significant_states, hass, start_time, None, entity_ids
            )
            plot_data: dict[str, list[tuple[float, float]]] = {}
            for eid, state_list in states.items():
                points: list[tuple[float, float]] = []
                for s in state_list:
                    try:
                        points.append((s.last_updated.timestamp(), float(s.state)))
                    except (ValueError, TypeError):
                        continue
                plot_data[eid] = points
            el["_plot_data"] = plot_data
        except Exception:
            _LOGGER.warning("Recorder not available, plot will render as placeholder")
            el["_plot_data"] = {}


async def render_drawcustom(
    hass: HomeAssistant,
    payload: list[dict[str, Any]],
    width: int,
    height: int,
    background: str = "white",
    rotate: int = 0,
    dither: str = "floyd-steinberg",
) -> tuple[Image.Image, Image.Image | None]:
    """Render a drawcustom payload to a PIL Image and optional dither mask.

    Public async entry point: resolves Jinja templates, downloads images,
    pre-fetches plot history, then runs Pillow work in an executor.

    Returns (canvas_rgb, dither_mask). dither_mask is None when no element
    has a per-element dither override.
    """
    # Resolve templates
    resolved = await _resolve_templates(hass, payload)

    # Pre-download HTTP images
    downloaded = await _download_images(hass, resolved)

    # Pre-fetch plot history data
    await _prefetch_plot_data(hass, resolved)

    # Run sync Pillow rendering in executor
    return await hass.async_add_executor_job(
        _render_sync, resolved, width, height, background, rotate, downloaded, dither,
    )
