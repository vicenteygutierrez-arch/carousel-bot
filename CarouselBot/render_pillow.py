"""
render_pillow.py — Renderiza carruseles profesionales con Pillow.
Genera slides atractivos con gradientes, tipografía sofisticada y diseño moderno.
"""
import argparse, colorsys, json, os, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

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
    if s < 0.12: return "neutral"
    deg = h * 360
    return "warm" if (deg < 60 or deg >= 300) else "cool"

def derive_tokens(primary_hex):
    family = hue_family(primary_hex)
    brand_light = lighten(primary_hex, 0.25)
    brand_dark = darken(primary_hex, 0.35)
    if family == "warm":
        light_bg = "#FBF9F5"; light_border = "#F0EBE0"; dark_bg = "#0D0C0B"
        accent = lighten(primary_hex, 0.15)
    elif family == "cool":
        light_bg = "#F7F8FB"; light_border = "#E5E9F2"; dark_bg = "#0A0E1A"
        accent = lighten(primary_hex, 0.15)
    else:
        light_bg = "#F8F7F3"; light_border = "#EBE9DE"; dark_bg = "#06060A"
        accent = "#D4A574"
    return {
        "BRAND_PRIMARY": primary_hex,
        "BRAND_LIGHT": brand_light,
        "BRAND_DARK": brand_dark,
        "LIGHT_BG": light_bg,
        "LIGHT_BORDER": light_border,
        "DARK_BG": dark_bg,
        "ACCENT": accent,
        "GRADIENT_START": brand_dark,
        "GRADIENT_MID": primary_hex,
        "GRADIENT_END": accent,
        "FAMILY": family,
    }

W, H = 1080, 1350
SCALE = W / 420.0
PAD_X = int(40 * SCALE)
PAD_BOTTOM = int(60 * SCALE)

def f(size, bold=False):
    """Carga font con fallback."""
    paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Windows/Fonts/arial.ttf",
    ]
    for path in paths:
        try: return ImageFont.truetype(path, int(size * SCALE))
        except: pass
    return ImageFont.load_default()

def rgb(hex_color, alpha=255):
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, alpha)

def gradient_bg(tok):
    """Gradiente diagonal profesional."""
    try:
        import numpy as np
    except:
        return Image.new("RGB", (W, H), hex_to_rgb(tok["GRADIENT_START"]))

    import math
    angle = math.radians(165 - 90)
    dx = math.cos(angle); dy = math.sin(angle)
    xs = np.arange(W, dtype=np.float32)
    ys = np.arange(H, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    proj = (xg * dx + yg * dy)
    proj -= proj.min()
    proj /= max(proj.max(), 1e-6)

    start = np.array(hex_to_rgb(tok["GRADIENT_START"]), dtype=np.float32)
    mid = np.array(hex_to_rgb(tok["GRADIENT_MID"]), dtype=np.float32)
    end = np.array(hex_to_rgb(tok["GRADIENT_END"]), dtype=np.float32)

    t = proj[..., None]
    below = t < 0.5
    t1 = np.clip(t * 2, 0, 1)
    t2 = np.clip((t - 0.5) * 2, 0, 1)
    col_lo = start * (1 - t1) + mid * t1
    col_hi = mid * (1 - t2) + end * t2
    out = np.where(below, col_lo, col_hi).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")

def wrap_text(text, font, max_w, draw):
    """Word-wrap con mejor espaciado."""
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def draw_text_lines(draw, text, x, y, font, color, max_w, line_height_mult=1.15):
    """Dibuja texto con mejor espaciado."""
    lines = wrap_text(text, font, max_w, draw)
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * line_height_mult)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_h), line, font=font, fill=color)
    return y + len(lines) * line_h

def draw_progress_bar(draw, idx, total, variant, tok):
    """Progress bar profesional."""
    y = H - int(40 * SCALE)
    bar_h = max(4, int(4 * SCALE))
    bar_x, bar_w = PAD_X, W - PAD_X - int(70 * SCALE)
    if variant == "light":
        track, fill, label = (0, 0, 0, 15), rgb(tok["BRAND_PRIMARY"]), (0, 0, 0, 80)
    else:
        track, fill, label = (255, 255, 255, 25), (255, 255, 255, 255), (255, 255, 255, 110)
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([bar_x, y, bar_x + bar_w, y + bar_h], radius=bar_h, fill=track)
    pct = (idx + 1) / total
    od.rounded_rectangle([bar_x, y, bar_x + int(bar_w * pct), y + bar_h], radius=bar_h, fill=fill)
    lbl = f"{idx+1}/{total}"
    lfont = f(11, bold=True)
    lbl_bbox = od.textbbox((0,0), lbl, font=lfont)
    od.text((W - PAD_X - (lbl_bbox[2] - lbl_bbox[0]), y - int(8*SCALE)), lbl, font=lfont, fill=label)
    return overlay

def render_hero(slide, idx, total, tok, is_last):
    """Hero slide con gradiente y tipografía grande."""
    img = Image.new("RGB", (W, H), hex_to_rgb(tok["LIGHT_BG"]))
    draw = ImageDraw.Draw(img)
    y = int(200 * SCALE)
    tag_font = f(12, bold=True)
    tag_bbox = draw.textbbox((0,0), slide.get("tag", "").upper(), font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    draw.text(((W - tag_w)//2, y), slide.get("tag", "").upper(), font=tag_font, fill=rgb(tok["BRAND_PRIMARY"]))
    y += int(50 * SCALE)
    font_head = f(42, bold=True)
    max_w = W - 2 * PAD_X
    lines = wrap_text(slide.get("heading", ""), font_head, max_w, draw)
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font_head)
        draw.text(((W - (bbox[2]-bbox[0]))//2, y), line, font=font_head, fill=rgb(tok["BRAND_DARK"]))
        y += int(60 * SCALE)
    img = img.convert("RGBA")
    img.alpha_composite(draw_progress_bar(ImageDraw.Draw(img), idx, total, "light", tok), (0, 0))
    return img

def render_context(slide, idx, total, tok, is_last):
    """Context slide oscuro con contenido."""
    img = Image.new("RGB", (W, H), hex_to_rgb(tok["DARK_BG"]))
    draw = ImageDraw.Draw(img)
    y = int(160 * SCALE)
    tag_font = f(11, bold=True)
    draw.text((PAD_X, y), slide.get("tag", "").upper(), font=tag_font, fill=rgb(tok["ACCENT"]))
    y += int(40 * SCALE)
    font_head = f(32, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head, (255, 255, 255, 255), max_w, 1.1)
    y += int(24 * SCALE)
    font_body = f(15)
    draw_text_lines(draw, slide.get("body", ""), PAD_X, y, font_body, (220, 220, 220, 220), max_w, 1.5)
    img = img.convert("RGBA")
    img.alpha_composite(draw_progress_bar(ImageDraw.Draw(img), idx, total, "dark", tok), (0, 0))
    return img

def render_gradient(slide, idx, total, tok, is_last):
    """Slide con gradiente y quote."""
    img = gradient_bg(tok).convert("RGBA")
    draw = ImageDraw.Draw(img)
    y = int(140 * SCALE)
    tag_font = f(11, bold=True)
    draw.text((PAD_X, y), slide.get("tag", "").upper(), font=tag_font, fill=(255, 255, 255, 200))
    y += int(40 * SCALE)
    font_head = f(34, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head, (255, 255, 255, 255), max_w, 1.08)
    y += int(28 * SCALE)
    font_body = f(15)
    y = draw_text_lines(draw, slide.get("body", ""), PAD_X, y, font_body, (240, 240, 240, 230), max_w, 1.5)
    if slide.get("quote"):
        y += int(24 * SCALE)
        box_pad = int(20 * SCALE)
        qfont = f(16)
        q_text = f'"{slide.get("quote")}"'
        lines = wrap_text(q_text, qfont, max_w - 2 * box_pad, draw)
        ascent, descent = qfont.getmetrics()
        lh = int((ascent + descent) * 1.4)
        box_h = len(lines) * lh + 2 * box_pad
        box = Image.new("RGBA", (max_w, box_h), (255, 255, 255, 12))
        bd = ImageDraw.Draw(box)
        bd.rounded_rectangle([0, 0, max_w, box_h], radius=int(16*SCALE), fill=(255, 255, 255, 12), outline=(255, 255, 255, 40), width=2)
        for i, line in enumerate(lines):
            bd.text((box_pad, box_pad + i * lh), line, font=qfont, fill=(255, 255, 255, 250))
        img.alpha_composite(box, (PAD_X, y))
    img.alpha_composite(draw_progress_bar(ImageDraw.Draw(img), idx, total, "dark", tok), (0, 0))
    return img

def render_features(slide, idx, total, tok, is_last):
    """Features slide con bullets y descripción."""
    img = Image.new("RGB", (W, H), hex_to_rgb(tok["LIGHT_BG"]))
    draw = ImageDraw.Draw(img)
    y = int(120 * SCALE)
    draw.text((PAD_X, y), slide.get("tag", "").upper(), font=f(11, bold=True), fill=rgb(tok["BRAND_PRIMARY"]))
    y += int(40 * SCALE)
    font_head = f(28, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head, rgb(tok["BRAND_DARK"]), max_w, 1.08)
    y += int(32 * SCALE)
    label_font = f(14, bold=True)
    desc_font = f(13)
    accent_c = rgb(tok["ACCENT"])
    dark_c = rgb(tok["BRAND_DARK"])
    mid_c = (110, 105, 100, 255)
    for item in slide.get("items", []):
        bx, by = PAD_X + int(10 * SCALE), y + int(12 * SCALE)
        bs = int(7 * SCALE)
        draw.polygon([(bx, by - bs), (bx + bs, by), (bx, by + bs), (bx - bs, by)], fill=accent_c)
        text_x = PAD_X + int(40 * SCALE)
        text_w = W - text_x - PAD_X
        label = item.get("label", "")
        desc = item.get("description", "")
        label_text = f"{label} — "
        draw.text((text_x, y), label_text, font=label_font, fill=dark_c)
        lb = draw.textbbox((0,0), label_text, font=label_font)
        lw = lb[2] - lb[0]
        remaining = desc
        first_w = text_w - lw
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
        draw.text((text_x + lw, y + int(3*SCALE)), line, font=desc_font, fill=mid_c)
        cy = y + int(18 * SCALE)
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
            if i2 == 0:
                line = rem_words[0]; i2 = 1
            draw.text((text_x, cy), line, font=desc_font, fill=mid_c)
            cy += int(16 * 1.3 * SCALE)
            rem_words = rem_words[i2:]
        y = max(cy, y + int(50 * SCALE))
    img = img.convert("RGBA")
    img.alpha_composite(draw_progress_bar(ImageDraw.Draw(img), idx, total, "light", tok), (0, 0))
    return img

def render_proof(slide, idx, total, tok, is_last):
    """Proof slide con pasos numerados."""
    img = Image.new("RGB", (W, H), hex_to_rgb(tok["LIGHT_BG"]))
    draw = ImageDraw.Draw(img)
    y = int(100 * SCALE)
    draw.text((PAD_X, y), slide.get("tag", "").upper(), font=f(11, bold=True), fill=rgb(tok["BRAND_PRIMARY"]))
    y += int(40 * SCALE)
    font_head = f(28, bold=True)
    max_w = W - 2 * PAD_X
    y = draw_text_lines(draw, slide.get("heading", ""), PAD_X, y, font_head, rgb(tok["BRAND_DARK"]), max_w, 1.08)
    y += int(24 * SCALE)
    num_font = f(22, bold=True)
    title_font = f(14, bold=True)
    desc_font = f(13)
    accent_c = rgb(tok["ACCENT"])
    dark_c = rgb(tok["BRAND_DARK"])
    mid_c = (110, 105, 100, 255)
    for s in slide.get("steps", []):
        draw.text((PAD_X, y + int(8 * SCALE)), s.get("number", ""), font=num_font, fill=accent_c)
        text_x = PAD_X + int(70 * SCALE)
        text_w = W - text_x - PAD_X
        title = s.get("title", "")
        desc = s.get("description", "")
        title_text = f"{title} — "
        draw.text((text_x, y), title_text, font=title_font, fill=dark_c)
        tb = draw.textbbox((0,0), title_text, font=title_font)
        tw = tb[2] - tb[0]
        words = desc.split()
        line = ""
        iw = 0
        while iw < len(words):
            test = (line + " " + words[iw]).strip()
            bb = draw.textbbox((0,0), test, font=desc_font)
            if bb[2]-bb[0] <= text_w - tw:
                line = test; iw += 1
            else:
                break
        draw.text((text_x + tw, y + int(3*SCALE)), line, font=desc_font, fill=mid_c)
        cy = y + int(18 * SCALE)
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
            cy += int(16 * 1.3 * SCALE)
            rem = rem[i2:]
        y = max(cy, y + int(60 * SCALE))
    img = img.convert("RGBA")
    img.alpha_composite(draw_progress_bar(ImageDraw.Draw(img), idx, total, "light", tok), (0, 0))
    return img

def render_cta(slide, idx, total, tok, is_last):
    """CTA slide con gradiente y botón."""
    img = gradient_bg(tok).convert("RGBA")
    draw = ImageDraw.Draw(img)
    max_w = W - 2 * PAD_X
    tag = slide.get("tag", "")
    heading = slide.get("heading", "")
    body = slide.get("body", "")
    cta_text = slide.get("cta_text", "COMENTA INFO")
    font_head = f(36, bold=True)
    font_body = f(15)
    font_cta = f(14, bold=True)
    heading_lines = wrap_text(heading, font_head, max_w, draw)
    body_lines = wrap_text(body, font_body, max_w, draw)
    ah, dh = font_head.getmetrics(); head_lh = int((ah+dh)*1.1)
    ab, db = font_body.getmetrics(); body_lh = int((ab+db)*1.5)
    total_h = int(60 * SCALE) + len(heading_lines) * head_lh + int(28 * SCALE) + len(body_lines) * body_lh + int(40 * SCALE) + int(70 * SCALE)
    y = max(int(150 * SCALE), (H - total_h) // 2)
    tfont = f(11, bold=True)
    tbb = draw.textbbox((0,0), tag.upper(), font=tfont)
    tw = tbb[2] - tbb[0] + int(2 * SCALE * max(0, len(tag)-1))
    for ln in heading_lines:
        bb = draw.textbbox((0,0), ln, font=font_head)
        lw = bb[2]-bb[0]
        draw.text(((W-lw)//2, y), ln, font=font_head, fill=(255,255,255,255))
        y += head_lh
    y += int(24 * SCALE)
    for ln in body_lines:
        bb = draw.textbbox((0,0), ln, font=font_body)
        lw = bb[2]-bb[0]
        draw.text(((W-lw)//2, y), ln, font=font_body, fill=(240,240,240,230))
        y += body_lh
    y += int(40 * SCALE)
    pb = draw.textbbox((0,0), cta_text, font=font_cta)
    pw = pb[2]-pb[0]; ph = pb[3]-pb[1]
    arrow_gap = int(14 * SCALE)
    arrow_size = int(16 * SCALE)
    pill_pad_x = int(32 * SCALE); pill_pad_y = int(16 * SCALE)
    pill_w = pw + arrow_gap + arrow_size + 2 * pill_pad_x
    pill_h = ph + 2 * pill_pad_y
    px = (W - pill_w) // 2
    py = y
    pill = Image.new("RGBA", (pill_w, pill_h), (0,0,0,0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle([0, 0, pill_w, pill_h], radius=pill_h//2, fill=(255,255,255,255))
    dark = rgb(tok["BRAND_DARK"])
    pd.text((pill_pad_x, pill_pad_y - int(4*SCALE)), cta_text, font=font_cta, fill=dark)
    ax0 = pill_pad_x + pw + arrow_gap
    ay_center = pill_h // 2
    a_sw = max(3, int(2.5 * SCALE))
    pd.line([(ax0, ay_center + arrow_size//2), (ax0 + arrow_size, ay_center - arrow_size//2)], fill=dark, width=a_sw)
    tip = (ax0 + arrow_size, ay_center - arrow_size//2)
    pd.line([tip, (tip[0] - arrow_size//2, tip[1])], fill=dark, width=a_sw)
    pd.line([tip, (tip[0], tip[1] + arrow_size//2)], fill=dark, width=a_sw)
    img.alpha_composite(pill, (px, py))
    img.alpha_composite(draw_progress_bar(ImageDraw.Draw(img), idx, total, "dark", tok), (0, 0))
    return img

RENDERERS = {
    "hero": render_hero,
    "context": render_context,
    "insight": render_gradient,
    "features": render_features,
    "depth": render_context,
    "proof": render_proof,
    "cta": render_cta,
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--primary", default="#1E40AF")
    args = ap.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    tok = derive_tokens(args.primary)
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    total = len(data["slides"])
    for i, slide in enumerate(data["slides"]):
        t = slide.get("type", "context")
        renderer = RENDERERS.get(t, render_context)
        is_last = (i == total - 1)
        img = renderer(slide, i, total, tok, is_last)
        out_path = out_dir / f"slide_{i+1:02d}.png"
        img.convert("RGB").save(out_path, "PNG", optimize=True)
        print(f"✅ {out_path.name}")

if __name__ == "__main__":
    main()
