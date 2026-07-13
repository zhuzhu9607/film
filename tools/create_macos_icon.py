from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


def main():
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    source_path = assets / "filmstrip-icon-source.png"
    if not source_path.exists():
        source_path = assets / "filmstrip-icon.png"

    image = Image.open(source_path).convert("RGBA")
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = ImageEnhance.Contrast(image).enhance(1.04)
    image = image.filter(ImageFilter.UnsharpMask(radius=0.7, percent=105, threshold=2))
    image = image.resize((1024, 1024), Image.Resampling.LANCZOS)

    output = assets / "filmstrip.icns"
    image.save(output, format="ICNS")
    print(output)


if __name__ == "__main__":
    main()
