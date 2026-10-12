"""Draw the app icon and save it as icon.ico (needs Pillow).

    py make_icon.py

A white download arrow dropping into a tray, on a blue-to-violet rounded tile.
Drawn large and scaled down so every size in the .ico has smooth edges.
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
TOP_LEFT, BOTTOM_RIGHT = (56, 152, 255), (112, 72, 240)


def gradient() -> Image.Image:
    """Diagonal blend between the two tile colours."""
    ramp = Image.linear_gradient("L").resize((SIZE * 2, SIZE * 2)).rotate(45).crop(
        (SIZE // 2, SIZE // 2, SIZE // 2 + SIZE, SIZE // 2 + SIZE))
    return Image.composite(Image.new("RGB", (SIZE, SIZE), BOTTOM_RIGHT), Image.new("RGB", (SIZE, SIZE), TOP_LEFT), ramp)


def draw_icon() -> Image.Image:
    tile = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(tile).rounded_rectangle((40, 40, SIZE - 40, SIZE - 40), radius=230, fill=255)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(gradient(), (0, 0), tile)

    draw = ImageDraw.Draw(icon)
    white = (255, 255, 255, 255)
    # arrow: shaft and head
    draw.rounded_rectangle((456, 200, 568, 520), radius=56, fill=white)
    draw.polygon([(312, 452), (712, 452), (512, 672)], fill=white)
    # tray: two short walls joined by a floor
    draw.rounded_rectangle((232, 600, 332, 824), radius=50, fill=white)
    draw.rounded_rectangle((692, 600, 792, 824), radius=50, fill=white)
    draw.rounded_rectangle((232, 724, 792, 824), radius=50, fill=white)
    return icon


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "icon.ico"
    draw_icon().save(target, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("Saved", target)
