"""Render the integration's original house/needle mark as a transparent PNG."""

from pathlib import Path
from shutil import copyfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def main():
    image = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(image)
    draw.line([(160, 440), (512, 148), (864, 440)], fill="#00a5a8", width=64)
    draw.line(
        [(244, 412), (244, 820), (780, 820), (780, 412)], fill="#00a5a8", width=64
    )
    draw.line([(400, 722), (600, 390)], fill="#e23b58", width=56)
    draw.ellipse((560, 320, 670, 430), outline="#e23b58", width=32)
    path = ROOT / "custom_components/needle/brand"
    path.mkdir(parents=True, exist_ok=True)
    image.resize((256, 256), Image.Resampling.LANCZOS).save(path / "icon.png")
    image.resize((512, 512), Image.Resampling.LANCZOS).save(path / "icon@2x.png")
    # The same transparent colors work on both light and dark backgrounds.
    copyfile(path / "icon.png", path / "dark_icon.png")
    copyfile(path / "icon@2x.png", path / "dark_icon@2x.png")


if __name__ == "__main__":
    main()
