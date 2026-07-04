#!/usr/bin/env python3
"""Build a square tile icon by stacking a wide logo's emblem above its wordmark.

Splits a horizontal logo (SVG or PNG) at the widest internal whitespace gap,
puts the right-hand part (emblem) centered on top and the left-hand part
(wordmark) centered below, then writes a square transparent PNG.

Usage:
    scripts/make-stacked-icon.py <logo.svg|logo.png> [output.png]

    output.png defaults to icon.png in the repo root.

Options via env vars:
    ICON_SIZE=600        output width/height in px
    ICON_MARGIN=0.06     margin as a fraction of the composition's longest side
    EMBLEM_SCALE=1.35    emblem height relative to wordmark height
    STACK_GAP=0.35       vertical gap as a fraction of wordmark height

Pillow is auto-installed into scripts/.pylib on first run (shared with
make-icon.py). SVGs are rendered via macOS Quick Look.
"""

import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYLIB = os.path.join(REPO_ROOT, "scripts", ".pylib")


def ensure_pillow():
    sys.path.insert(0, PYLIB)
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Installing Pillow into scripts/.pylib ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--target", PYLIB, "pillow"]
        )


def render_svg(svg_path, workdir, size=1024):
    subprocess.check_call(
        ["qlmanage", "-t", "-s", str(size), "-o", workdir, svg_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    out = os.path.join(workdir, os.path.basename(svg_path) + ".png")
    if not os.path.exists(out):
        sys.exit(f"qlmanage did not produce {out} — is the SVG valid?")
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    dest = sys.argv[2] if len(sys.argv) > 2 else os.path.join(REPO_ROOT, "icon.png")
    size = int(os.environ.get("ICON_SIZE", "600"))
    margin = float(os.environ.get("ICON_MARGIN", "0.06"))
    emblem_scale = float(os.environ.get("EMBLEM_SCALE", "1.35"))
    gap_frac = float(os.environ.get("STACK_GAP", "0.35"))

    ensure_pillow()
    from PIL import Image, ImageChops

    def trim(img):
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        flat = Image.alpha_composite(white, img).convert("RGB")
        box = ImageChops.difference(flat, white.convert("RGB")).getbbox()
        if not box:
            sys.exit("Image appears to be blank (all white/transparent).")
        return img.crop(box)

    with tempfile.TemporaryDirectory() as workdir:
        path = render_svg(src, workdir) if src.lower().endswith(".svg") else src
        logo = trim(Image.open(path).convert("RGBA"))
        w, h = logo.size

        # find the widest run of empty (white/transparent) columns, away from the edges
        white = Image.new("RGBA", logo.size, (255, 255, 255, 255))
        flat = Image.alpha_composite(white, logo).convert("RGB")
        px = flat.load()
        empty = [
            all(px[x, y] == (255, 255, 255) for y in range(0, h, 2)) for x in range(w)
        ]
        runs, start = [], None
        for x, e in enumerate(empty):
            if e and start is None:
                start = x
            if not e and start is not None:
                runs.append((start, x))
                start = None
        gaps = [(a, b) for a, b in runs if w * 0.15 < a and b < w * 0.9]
        if not gaps:
            sys.exit("No internal whitespace gap found to split the logo at.")
        a, b = max(gaps, key=lambda g: g[1] - g[0])
        wordmark = trim(logo.crop((0, 0, a, h)))
        emblem = trim(logo.crop((b, 0, w, h)))

        s = emblem_scale * wordmark.size[1] / emblem.size[1]
        emblem = emblem.resize(
            (round(emblem.size[0] * s), round(emblem.size[1] * s)), Image.LANCZOS
        )

        gap = round(wordmark.size[1] * gap_frac)
        W = max(wordmark.size[0], emblem.size[0])
        H = emblem.size[1] + gap + wordmark.size[1]
        stack = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        stack.paste(emblem, ((W - emblem.size[0]) // 2, 0), emblem)
        stack.paste(wordmark, ((W - wordmark.size[0]) // 2, emblem.size[1] + gap), wordmark)

        side = round(max(W, H) * (1 + 2 * margin))
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(stack, ((side - W) // 2, (side - H) // 2), stack)
        canvas.resize((size, size), Image.LANCZOS).save(dest)

    print(f"Wrote {dest} ({size}x{size}; emblem {emblem.size}, wordmark {wordmark.size})")


if __name__ == "__main__":
    main()
