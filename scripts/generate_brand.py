"""Build integration icon sizes from the house-and-cactus master image."""

from pathlib import Path
from shutil import copyfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    with Image.open(ROOT / "assets/needle-home-assistant.png") as source:
        image = source.convert("RGBA")
    path = ROOT / "custom_components/needle/brand"
    path.mkdir(parents=True, exist_ok=True)
    image.resize((256, 256), Image.Resampling.LANCZOS).save(path / "icon.png")
    image.resize((512, 512), Image.Resampling.LANCZOS).save(path / "icon@2x.png")
    # The same transparent colors work on both light and dark backgrounds.
    copyfile(path / "icon.png", path / "dark_icon.png")
    copyfile(path / "icon@2x.png", path / "dark_icon@2x.png")


if __name__ == "__main__":
    main()
