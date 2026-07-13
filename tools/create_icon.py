import argparse
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48),
              (64, 64), (128, 128), (256, 256)]


def main():
    parser = argparse.ArgumentParser(description="Create the Windows app icon from artwork.")
    parser.add_argument("source", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    assets.mkdir(exist_ok=True)

    image = Image.open(args.source).convert("RGBA")
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = ImageEnhance.Contrast(image).enhance(1.04)
    image = image.filter(ImageFilter.UnsharpMask(radius=0.7, percent=105, threshold=2))
    image = image.resize((1024, 1024), Image.Resampling.LANCZOS)

    preview = image.resize((512, 512), Image.Resampling.LANCZOS)
    preview.save(assets / "filmstrip-icon.png", optimize=True)
    image.save(assets / "filmstrip.ico", format="ICO", sizes=ICON_SIZES)
    print(assets / "filmstrip.ico")


if __name__ == "__main__":
    main()
