"""Render home-assistant/brands assets for the resideo_shutoff_valve integration.

Draws a neutral water shut-off valve handwheel (universal shut-off symbol) on a
rounded water-blue tile. Not an imitation of any official Resideo/Honeywell mark.
"""
import math

from PIL import Image, ImageDraw

SS = 4  # supersample factor for anti-aliasing


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def draw_icon(size):
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # --- rounded tile with vertical blue gradient ---
    top = (34, 150, 226)     # lighter water blue
    bot = (10, 96, 178)      # deeper blue
    grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gpx = grad.load()
    for y in range(S):
        c = lerp(top, bot, y / (S - 1)) + (255,)
        for x in range(S):
            gpx[x, y] = c
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    margin = round(0.05 * S)
    radius = round(0.22 * S)
    md.rounded_rectangle([margin, margin, S - margin, S - margin],
                         radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    W = (245, 249, 252, 255)  # near-white

    cx = S / 2
    # ---- pipe across the lower body ----
    pipe_y = 0.70 * S
    pipe_h = 0.115 * S
    pipe_x0, pipe_x1 = 0.20 * S, 0.80 * S
    d.rounded_rectangle([pipe_x0, pipe_y - pipe_h / 2, pipe_x1, pipe_y + pipe_h / 2],
                        radius=pipe_h / 2, fill=W)
    # pipe end flanges
    fl_w = 0.035 * S
    fl_h = 0.185 * S
    for fx in (pipe_x0 - fl_w * 0.2, pipe_x1 - fl_w * 0.8):
        d.rounded_rectangle([fx, pipe_y - fl_h / 2, fx + fl_w, pipe_y + fl_h / 2],
                            radius=fl_w / 3, fill=W)

    # ---- valve body (trapezoid) connecting pipe to stem ----
    body_top_y = 0.52 * S
    d.polygon([
        (cx - 0.055 * S, body_top_y),
        (cx + 0.055 * S, body_top_y),
        (cx + 0.10 * S, pipe_y - pipe_h * 0.15),
        (cx - 0.10 * S, pipe_y - pipe_h * 0.15),
    ], fill=W)

    # ---- stem ----
    stem_w = 0.055 * S
    wheel_cy = 0.335 * S
    d.rounded_rectangle(
        [cx - stem_w / 2, wheel_cy, cx + stem_w / 2, body_top_y + 0.01 * S],
        radius=stem_w / 2,
        fill=W,
    )

    # ---- handwheel ----
    R = 0.205 * S           # outer radius
    ring_w = 0.052 * S      # rim thickness
    d.ellipse([cx - R, wheel_cy - R, cx + R, wheel_cy + R],
              outline=W, width=round(ring_w))
    # spokes (4, at 45deg offsets for a classic look)
    spoke_w = round(0.042 * S)
    inner = R - ring_w * 0.4
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        d.line([(cx, wheel_cy),
                (cx + inner * math.cos(a), wheel_cy + inner * math.sin(a))],
               fill=W, width=spoke_w)
    # hub
    hub = 0.072 * S
    d.ellipse([cx - hub, wheel_cy - hub, cx + hub, wheel_cy + hub], fill=W)

    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    import sys
    out = sys.argv[1]
    draw_icon(512).save(f"{out}/icon@2x.png")
    draw_icon(256).save(f"{out}/icon.png")
    print("wrote icon.png (256) and icon@2x.png (512)")
