#!/usr/bin/env python3
"""Convert a logo (SVG or PNG) into a square tile icon.

Renders SVGs via macOS Quick Look (qlmanage), trims any white/transparent
border, centers the logo on a square transparent canvas with a margin, and
writes a PNG sized for an Ops Manager tile icon.

Usage:
    scripts/make-icon.py <logo.svg|logo.png> [output.png]

    output.png defaults to icon.png in the repo root (what `kiln bake` embeds).

Options via env vars:
    ICON_SIZE=512     output width/height in px
    ICON_MARGIN=0.15  margin around the logo as a fraction of its longest side

Pillow is auto-installed into scripts/.pylib on first run.
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
    """Render an SVG to PNG using macOS Quick Look."""
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
    size = int(os.environ.get("ICON_SIZE", "512"))
    margin = float(os.environ.get("ICON_MARGIN", "0.15"))

    ensure_pillow()
    from PIL import Image, ImageChops

    with tempfile.TemporaryDirectory() as workdir:
        path = render_svg(src, workdir) if src.lower().endswith(".svg") else src
        im = Image.open(path).convert("RGBA")

        # Trim border: content is whatever differs from solid white after
        # compositing, so both white and transparent padding are removed.
        white = Image.new("RGBA", im.size, (255, 255, 255, 255))
        flat = Image.alpha_composite(white, im)
        bbox = ImageChops.difference(flat.convert("RGB"), white.convert("RGB")).getbbox()
        if not bbox:
            sys.exit("Logo appears to be blank (all white/transparent).")
        logo = im.crop(bbox)

        w, h = logo.size
        side = int(max(w, h) * (1 + 2 * margin))
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(logo, ((side - w) // 2, (side - h) // 2), logo)
        canvas.resize((size, size), Image.LANCZOS).save(dest)

    print(f"Wrote {dest} ({size}x{size}, logo content {w}x{h} from {src})")


if __name__ == "__main__":
    main()
