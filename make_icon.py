"""Build icon.ico from icon.png, the app icon artwork (needs Pillow).

    py make_icon.py

icon.png is the 512x512 icon from the redesign: a mint folder with blue and
grey tabs and a download arrow. Every size Windows asks for is scaled down
from it, so each one has smooth edges.
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]

if __name__ == "__main__":
    artwork = Image.open(HERE / "icon.png").convert("RGBA")
    artwork.save(HERE / "icon.ico", sizes=[(size, size) for size in SIZES])
    print("Saved", HERE / "icon.ico")
