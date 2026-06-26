"""
render_pillow.py — Render 7-slide IG carousel PNGs (1080x1350) using Pillow,
as a fallback when Playwright/Chromium isn't available in the sandbox.
Mirrors the design-system tokens derived by gen_carousel.py.

Usage:
    python3 scripts/render_pillow.py --input carousel_01/slides.json --out carousel_01/slides_new
"""
import argparse
import colorsys
import json
import os
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---------- Color utilities (copied from gen_carousel.py) ----------

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(c))) for c in rgb))

def lighten(hex_color, amount):
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = min(1.0, l + (1 - l) * amount)
    return rgb_to_hex(tuple(c * 255 for c in colorsys.hls_to_rgb(h, l, s)))

def darken(hex_color, amount):
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = max(0.0, l * (1 - amount))
    return rgb_to_hex(tuple(c * 255 for c in colorsys.hls_to_rgb(h, l, s)))

def hue_family(hex_color):
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    if s < 0.12:
        return "neutral"
    deg = h * 360
    if deg < 60 or deg >= 300:
        return "warm"
    return "cool"

def derive_tokens(primary_hex):
    family = hue_family(primary_hex)
    brand_light = lighten(primary_hex, 0.25)
    brand_dark = darken(primary_hex, 0.35)
    if family == "warm":
        light_bg = "#F7F5F0"; light_border = "#EAE6DC"; dark_bg = "#1A1918"
        accent = lighten(primary_hex, 0.15)
    elif family == "cool":
        light_bg = "#F4F5F7"; light_border = "#E1E4EA"; dark_bg = "#0F172A"
        accent = lighten(primary_hex, 0.15)
    else:
        light_bg = "#F5F4EE"; light_border = "#E6E4DB"; dark_bg = "#0D0D10"
        accent = "#D4A574"
    mid = "#2A2A30" if family == "neutral" else primary_hex
    return {
        "BRAND_PRIMARY": primary_hex,
        "BRAND_LIGHT": brand_light,
        "BRAND_DARK": brand_dark,
        "LIGHT_BG": light_bg,
        "LIGHT_BORDER": light_border,
        "DARK_BG": dark_bg,
        "ACCENT": accent,
        "GRADIENT_START": brand_dark,
        "GRADIENT_MID": mid,
        "GRADIENT_END": accent,
        "FAMILY": family,
    }

# ---------- Canvas & scale ----------

W, H = 1080, 1350                       # IG portrait
SCALE = W / 420.0                       # the HTML design uses 420px base width
PAD_X = int(36 * SCALE)                 # 36px padding → scaled
PAD_BOTTOM = int(52 * SCALE)            # room for progress bar

# ---------- Font loader ----------

def f(size, bold=False):
    """Load font with fallback to default if TrueType unavailable."""
    paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "/Windows/Fonts/arial.ttf",  # Windows
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, int(size * SCALE))
        except:
            pass
    return ImageFont.load_default()

# ---------- Helpers ----------

def rgb(hex_color, alpha=255):
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, alpha)

def rgba_over(hex_color, alpha):
    return rgb(hex_color, int(alpha * 255))

def mix(c1, c2, t):
    """Mix two hex colors with t in 0..1"""
    a = hex_to_rgb(c1); b = hex_to_rgb(c2)
    return rgb_to_hex(tuple(a[i] * (1-t) + b[i] * t for i in range(3)))

def gradient_bg(tok):
    """Produce a 1080x1350 diagonal gradient image using numpy for speed."""
    import math
    try:
        import numpy as np
    except ImportError:
        np = None

    if np is None:
        # slow fallback — only fill with brand dark solid
        return Image.new("RGB", (W, H), tok["GRADIENT_START"])

    # 165° → direction vector
    angle = math.radians(165 - 90)
    dx = math.cos(angle); dy = math.sin(angle)
    xs = np.arange(W, dtype=np.float32)
    ys = np.arange(H, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    proj = (xg * dx + yg * dy)
    proj -= proj.min()
    proj /= max(proj.max(), 1e-6)  # 0..1

    start = np.array(hex_to_rgb(tok["GRADIENT_START"]), dtype=np.float32)
    mid   = np.array(hex_to_rgb(tok["GRADIENT_MID"]),   dtype=np.float32)
    end   = np.array(hex_to_rgb(tok["GRADIENT_END"]),   dtype=np.float32)

    # Two-stop interpolation
    t = proj[..., None]
    # first half: start→mid, second half: mid→end
    below = t < 0.5
    t1 = np.clip(t * 2, 0, 1)
    t2 = np.clip((t - 0.5) * 2, 0, 1)
    col_lo = start * (1 - t1) + mid * t1
    col_hi = mid   * (1 - t2) + end * t2
    out = np.where(below, col_lo, col_hi).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")

def wrap_text(text, font, max_w, draw):
    """Word-wrap text to fit max_w pixels."""
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def draw_text_lines(draw, text, x, y, font, color, max_w, line_height_mult=1.1):
    lines = wrap_text(text, font, max_w, draw)
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * line_height_mult)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_h), line, font=font, fill=color)
    return y + len(lines) * line_h

def draw_tag(draw, text, x, y, color):
    """Small uppercase tag label — 10px @420 → ~26px @1080, letterspacing 2px scaled."""
    font = f(10, bold=True)
    # Pillow doesn't do letter-spacing natively; emulate by drawing char by char
    ls = int(2 * SCALE)
    cx = x
    for ch in text.upper():
        draw.text((cx, y), ch, font=font, fill=color)
        bbox = draw.textbbox((0,0), ch, font=font)
        cx += (bbox[2] - bbox[0]) + ls
    # Return y after tag + 20px margin
    return y + int((10 + 20) * SCALE)

def draw_progress_bar(draw, idx, total, variant, tok):
    """Bottom progress bar + N/7 label."""
    y = H - int(36 * SCALE)
    bar_h = max(3, int(3 * SCALE))
    bar_x = PAD_X
    bar_y = y
    bar_w = W - PAD_X - int(60 * SCALE)  # leave room for "N/7"
    if variant == "light":
        track = (0, 0, 0, 20)
        fill = rgb(tok["BRAND_PRIMARY"])
        label = (0, 0, 0, 90)
    else:
        track = (255, 255, 255, 30)
        fill = (255, 255, 255, 255)
        label = (255, 255, 255, 115)
    # Track
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=bar_h//2, fill=track)
    pct = (idx + 1) / total
    od.rounded_rectangle([bar_x, bar_y, bar_x + int(bar_w * pct), bar_y + bar_h], radius=bar_h//2, fill=fill)
    # Label
    lbl = f"{idx+1}/{total}"
    lfont = f(11, bold=True)
    lbl_bbox = od.textbbox((0,0), lbl, font=lfont)
    lbl_w = lbl_bbox[2] - lbl_bbox[0]
    od.text((W - PAD_X - lbl_w, bar_y - int(6*SCALE)), lbl, font=lfont, fill=label)
    return overlay

def draw_swipe_arrow(variant):
    """Right edge arrow gradient + chevron."""
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    aw = int(48 * SCALE)
    if variant == "light":
        grad_end = (0, 0, 0, 15); stroke = (0, 0, 0, 70)
    else:
        grad_end = (255, 255, 255, 20); stroke = (255, 255, 255, 90)
    # Soft gradient band
    for i in range(aw):
        alpha = int(grad_end[3] * (i / aw))
        od.rectangle([W - aw + i, 0, W - aw + i + 1, H], fill=(grad_end[0], grad_end[1], grad_end[2], alpha))
    # Chevron in the middle, pointing right
    cx = W - aw // 2
    cy = H // 2
    sw = max(4, int(2.5 * SCALE))
    size = int(12 * SCALE)
    # Draw ">" as two lines
    od.line([(cx - size//2, cy - size), (cx + size//2, cy), (cx - size//2, cy + size)],
            fill=stroke, width=sw, joint="curve")
    return overlay

def paste_over(base, overlay):
    if base.mode != "RGBA":
        base = base.convert("RGBA")
    base.alpha_composite(overlay)
    return base

# ---------- Slide renderers ----------

def render_hero(slide, idx, total, tok, is_last):
    img = Image.new("RGB", (W, H), tok["LIGHT_BG"])
    draw = ImageDraw.Draw(img)
    y = int(180 * SCALE)  # vertically centered-ish
    y = draw_tag(draw, slide.get("tag", ""), PAD_X, y, rgb(tok["BRAND_PRIMARY"]))
    font_head = f(34, bold=True)
    max_w = W - 2 * PAD_X
    draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head,
                    rgb(tok["BRAND_DARK"]), max_w, line_height_mult=1.08)
    img = img.convert("RGBA")
    img = paste_over(img, draw_progress_bar(ImageDraw.Draw(img), idx, total, "light", tok))
    if not is_last:
        img = paste_over(img, draw_swipe_arrow("light"))
    return img

def render_dark(slide, idx, total, tok, is_last, variant_color="#F5F4EE"):
    img = Image.new("RGB", (W, H), tok["DARK_BG"])
    draw = ImageDraw.Draw(img)
    y = int(180 * SCALE)
    y = draw_tag(draw, slide.get("tag", ""), PAD_X, y, rgb(tok["ACCENT"]))
    font_head = f(28, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head,
                        rgb(variant_color), max_w, line_height_mult=1.1)
    y += int(16 * SCALE)
    font_body = f(14)
    draw_text_lines(draw, slide.get("body", ""), PAD_X, y, font_body,
                    (245, 244, 238, 190), max_w, line_height_mult=1.55)
    img = img.convert("RGBA")
    img = paste_over(img, draw_progress_bar(ImageDraw.Draw(img), idx, total, "dark", tok))
    if not is_last:
        img = paste_over(img, draw_swipe_arrow("dark"))
    return img

def render_gradient(slide, idx, total, tok, is_last):
    img = gradient_bg(tok).convert("RGBA")
    draw = ImageDraw.Draw(img)
    y = int(170 * SCALE)
    y = draw_tag(draw, slide.get("tag", ""), PAD_X, y, (255, 255, 255, 190))
    font_head = f(30, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head,
                        (255, 255, 255, 255), max_w, line_height_mult=1.08)
    y += int(14 * SCALE)
    font_body = f(14)
    y = draw_text_lines(draw, slide.get("body", ""), PAD_X, y, font_body,
                        (255, 255, 255, 215), max_w, line_height_mult=1.5)
    quote = slide.get("quote")
    if quote:
        y += int(18 * SCALE)
        box_pad = int(16 * SCALE)
        qfont = f(14)
        q_text = f"\u201c{quote}\u201d"
        lines = wrap_text(q_text, qfont, max_w - 2 * box_pad, draw)
        ascent, descent = qfont.getmetrics()
        lh = int((ascent + descent) * 1.45)
        box_h = len(lines) * lh + 2 * box_pad
        # box
        box = Image.new("RGBA", (max_w, box_h), (0, 0, 0, 60))
        bd = ImageDraw.Draw(box)
        bd.rounded_rectangle([0, 0, max_w, box_h], radius=int(12*SCALE),
                             fill=(0, 0, 0, 60), outline=(255, 255, 255, 30), width=2)
        for i, line in enumerate(lines):
            bd.text((box_pad, box_pad + i * lh), line, font=qfont, fill=(255, 255, 255, 245))
        img.alpha_composite(box, (PAD_X, y))
    img = paste_over(img, draw_progress_bar(ImageDraw.Draw(img), idx, total, "dark", tok))
    if not is_last:
        img = paste_over(img, draw_swipe_arrow("dark"))
    return img

def render_features(slide, idx, total, tok, is_last):
    img = Image.new("RGB", (W, H), tok["LIGHT_BG"])
    draw = ImageDraw.Draw(img)
    y = int(140 * SCALE)
    y = draw_tag(draw, slide.get("tag", ""), PAD_X, y, rgb(tok["BRAND_PRIMARY"]))
    font_head = f(26, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head,
                        rgb(tok["BRAND_DARK"]), max_w, line_height_mult=1.08)
    y += int(14 * SCALE)
    items = slide.get("items", [])
    row_pad_y = int(11 * SCALE)
    label_font = f(13, bold=True)
    desc_font = f(12)
    border_c = rgb(tok["LIGHT_BORDER"])
    accent_c = rgb(tok["ACCENT"])
    dark_c = rgb(tok["BRAND_DARK"])
    mid_c = (107, 102, 94, 255)
    bullet_col_w = int(28 * SCALE)
    for item in items:
        # bullet — draw a small filled diamond (Liberation lacks ✦ glyph)
        bx = PAD_X + int(6 * SCALE)
        by = y + row_pad_y + int(8 * SCALE)
        bs = int(6 * SCALE)  # half-size
        draw.polygon([(bx, by - bs), (bx + bs, by), (bx, by + bs), (bx - bs, by)],
                     fill=accent_c)
        # label + desc wrapped
        text_x = PAD_X + bullet_col_w
        text_w = W - text_x - PAD_X
        label = item.get("label", "")
        desc = item.get("description", "")
        # label + em-dash inline, then description wraps below if it overflows
        first_line = f"{label} — {desc}"
        lines = wrap_text(first_line, desc_font, text_w, draw)
        # We want the "label — " portion bold, the rest regular. Simplest: draw label bold first, then rest wrapped.
        label_text = f"{label} — "
        lb = draw.textbbox((0,0), label_text, font=label_font)
        lw = lb[2] - lb[0]
        draw.text((text_x, y + row_pad_y), label_text, font=label_font, fill=dark_c)
        # Remaining desc — wrap, first line starts after label
        remaining = desc
        first_w = text_w - lw
        # word-wrap first line
        words = remaining.split()
        line = ""
        idx_w = 0
        while idx_w < len(words):
            test = (line + " " + words[idx_w]).strip()
            bb = draw.textbbox((0,0), test, font=desc_font)
            if bb[2]-bb[0] <= first_w:
                line = test
                idx_w += 1
            else:
                break
        draw.text((text_x + lw, y + row_pad_y + int(2*SCALE)), line, font=desc_font, fill=mid_c)
        # subsequent lines (full width)
        cy = y + row_pad_y + int((12 + 4) * SCALE)
        rem_words = words[idx_w:]
        while rem_words:
            line = ""
            i2 = 0
            while i2 < len(rem_words):
                test = (line + " " + rem_words[i2]).strip()
                bb = draw.textbbox((0,0), test, font=desc_font)
                if bb[2]-bb[0] <= text_w:
                    line = test; i2 += 1
                else:
                    break
            if i2 == 0:  # single word too long, force
                line = rem_words[0]; i2 = 1
            draw.text((text_x, cy), line, font=desc_font, fill=mid_c)
            cy += int((12 * 1.4) * SCALE)
            rem_words = rem_words[i2:]
        row_h = max(cy - y, row_pad_y * 2 + int(20 * SCALE))
        y += row_h
        # bottom border
        draw.line([(PAD_X, y), (W - PAD_X, y)], fill=border_c, width=1)
    img = img.convert("RGBA")
    img = paste_over(img, draw_progress_bar(ImageDraw.Draw(img), idx, total, "light", tok))
    if not is_last:
        img = paste_over(img, draw_swipe_arrow("light"))
    return img

def render_proof(slide, idx, total, tok, is_last):
    img = Image.new("RGB", (W, H), tok["LIGHT_BG"])
    draw = ImageDraw.Draw(img)
    y = int(120 * SCALE)
    y = draw_tag(draw, slide.get("tag", ""), PAD_X, y, rgb(tok["BRAND_PRIMARY"]))
    font_head = f(26, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head,
                        rgb(tok["BRAND_DARK"]), max_w, line_height_mult=1.08)
    y += int(12 * SCALE)
    steps = slide.get("steps", [])
    num_font = f(20, bold=True)
    title_font = f(13, bold=True)
    desc_font = f(12)
    border_c = rgb(tok["LIGHT_BORDER"])
    accent_c = rgb(tok["ACCENT"])
    dark_c = rgb(tok["BRAND_DARK"])
    mid_c = (107, 102, 94, 255)
    num_col_w = int(60 * SCALE)
    for s in steps:
        row_y = y + int(12 * SCALE)
        draw.text((PAD_X, row_y), s.get("number", ""), font=num_font, fill=accent_c)
        text_x = PAD_X + num_col_w
        text_w = W - text_x - PAD_X
        title = s.get("title", "")
        desc = s.get("description", "")
        # Title bold + " — " + desc regular wrapped
        title_text = f"{title} — "
        tb = draw.textbbox((0,0), title_text, font=title_font)
        tw = tb[2] - tb[0]
        draw.text((text_x, row_y), title_text, font=title_font, fill=dark_c)
        # wrap desc
        words = desc.split()
        first_w = text_w - tw
        line = ""; iw = 0
        while iw < len(words):
            test = (line + " " + words[iw]).strip()
            bb = draw.textbbox((0,0), test, font=desc_font)
            if bb[2]-bb[0] <= first_w:
                line = test; iw += 1
            else:
                break
        draw.text((text_x + tw, row_y + int(2*SCALE)), line, font=desc_font, fill=mid_c)
        cy = row_y + int((13 + 6) * SCALE)
        rem = words[iw:]
        while rem:
            line = ""; i2 = 0
            while i2 < len(rem):
                test = (line + " " + rem[i2]).strip()
                bb = draw.textbbox((0,0), test, font=desc_font)
                if bb[2]-bb[0] <= text_w:
                    line = test; i2 += 1
                else:
                    break
            if i2 == 0:
                line = rem[0]; i2 = 1
            draw.text((text_x, cy), line, font=desc_font, fill=mid_c)
            cy += int((12 * 1.4) * SCALE)
            rem = rem[i2:]
        y = max(cy, row_y + int(34 * SCALE))
        draw.line([(PAD_X, y), (W - PAD_X, y)], fill=border_c, width=1)
    img = img.convert("RGBA")
    img = paste_over(img, draw_progress_bar(ImageDraw.Draw(img), idx, total, "light", tok))
    if not is_last:
        img = paste_over(img, draw_swipe_arrow("light"))
    return img

def render_cta(slide, idx, total, tok, is_last):
    img = gradient_bg(tok).convert("RGBA")
    draw = ImageDraw.Draw(img)
    max_w = W - 2 * PAD_X
    # Center-aligned block: measure first, then draw vertically centered
    tag = slide.get("tag", "")
    heading = slide.get("heading", "")
    body = slide.get("body", "")
    cta_text = slide.get("cta_text", 'COMENTA "INFO"')
    font_head = f(30, bold=True)
    font_body = f(14)
    font_cta = f(13, bold=True)
    heading_lines = wrap_text(heading, font_head, max_w, draw)
    body_lines = wrap_text(body, font_body, max_w, draw)
    ah, dh = font_head.getmetrics(); head_lh = int((ah+dh)*1.1)
    ab, db = font_body.getmetrics(); body_lh = int((ab+db)*1.5)
    total_h = int(30 * SCALE) + len(heading_lines) * head_lh + int(14 * SCALE) + len(body_lines) * body_lh + int(24 * SCALE) + int(56 * SCALE)
    y = (H - total_h) // 2
    # Tag centered
    tfont = f(10, bold=True)
    tbb = draw.textbbox((0,0), tag.upper(), font=tfont)
    tw = tbb[2] - tbb[0] + int(2 * SCALE * max(0, len(tag)-1))
    draw_tag(draw, tag, (W - tw)//2, y, (255, 255, 255, 190))
    y += int(30 * SCALE)
    # Heading centered
    for ln in heading_lines:
        bb = draw.textbbox((0,0), ln, font=font_head)
        lw = bb[2]-bb[0]
        draw.text(((W-lw)//2, y), ln, font=font_head, fill=(255,255,255,255))
        y += head_lh
    y += int(14 * SCALE)
    # Body centered
    for ln in body_lines:
        bb = draw.textbbox((0,0), ln, font=font_body)
        lw = bb[2]-bb[0]
        draw.text(((W-lw)//2, y), ln, font=font_body, fill=(255,255,255,215))
        y += body_lh
    y += int(24 * SCALE)
    # CTA pill — draw arrow as vector instead of unicode glyph
    pill_text = cta_text
    pb = draw.textbbox((0,0), pill_text, font=font_cta)
    pw = pb[2]-pb[0]; ph = pb[3]-pb[1]
    arrow_gap = int(12 * SCALE)
    arrow_size = int(14 * SCALE)
    pill_pad_x = int(28 * SCALE); pill_pad_y = int(14 * SCALE)
    pill_w = pw + arrow_gap + arrow_size + 2 * pill_pad_x
    pill_h = ph + 2 * pill_pad_y
    px = (W - pill_w) // 2
    py = y
    pill = Image.new("RGBA", (pill_w, pill_h), (0,0,0,0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle([0, 0, pill_w, pill_h], radius=pill_h//2, fill=(255,255,255,255))
    dark = rgb(tok["BRAND_DARK"])
    pd.text((pill_pad_x, pill_pad_y - int(4*SCALE)), pill_text, font=font_cta, fill=dark)
    # Arrow ↗ as two lines: a slash from bottom-left to top-right + chevron head
    ax0 = pill_pad_x + pw + arrow_gap
    ay_center = pill_h // 2
    a_sw = max(3, int(2.2 * SCALE))
    # diagonal line
    pd.line([(ax0, ay_center + arrow_size//2),
             (ax0 + arrow_size, ay_center - arrow_size//2)],
            fill=dark, width=a_sw)
    # head — two small lines at the tip
    tip = (ax0 + arrow_size, ay_center - arrow_size//2)
    pd.line([tip, (tip[0] - arrow_size//2, tip[1])], fill=dark, width=a_sw)
    pd.line([tip, (tip[0], tip[1] + arrow_size//2)], fill=dark, width=a_sw)
    img.alpha_composite(pill, (px, py))
    img = paste_over(img, draw_progress_bar(ImageDraw.Draw(img), idx, total, "dark", tok))
    return img

RENDERERS = {
    "hero":     render_hero,
    "context":  render_dark,
    "insight":  render_gradient,
    "features": render_features,
    "depth":    render_dark,
    "proof":    render_proof,
    "cta":      render_cta,
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--primary", default="#18181B")
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    tok = derive_tokens(args.primary)
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    total = len(data["slides"])
    for i, slide in enumerate(data["slides"]):
        t = slide.get("type", "context")
        renderer = RENDERERS.get(t, render_dark)
        is_last = (i == total - 1)
        img = renderer(slide, i, total, tok, is_last)
        out_path = out_dir / f"slide_{i+1:02d}.png"
        img.convert("RGB").save(out_path, "PNG", optimize=True)
        print(f"wrote {out_path}")

if __name__ == "__main__":
    main()
