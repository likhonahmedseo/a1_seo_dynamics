from __future__ import annotations

from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CANDIDATES = [
    PROJECT_ROOT / "logo.png",
    PROJECT_ROOT / "assets" / "app logo.png",
]
OUTPUT_ICO = PROJECT_ROOT / "assets" / "icon.ico"
OUTPUT_ICNS = PROJECT_ROOT / "assets" / "icon.icns"
OUTPUT_DESKTOP_PNG = PROJECT_ROOT / "assets" / "app-icon-512.png"
OUTPUT_WEB_PNG = PROJECT_ROOT / "client" / "public" / "app-icon.png"
OUTPUT_APPLE_PNG = PROJECT_ROOT / "client" / "public" / "apple-touch-icon.png"


def _find_source() -> Path:
    for candidate in SOURCE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No icon source image was found. Expected one of: "
        + ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in SOURCE_CANDIDATES)
    )


def _remove_near_white_background(image: Image.Image, threshold: int = 245) -> Image.Image:
    rgba = image.convert("RGBA")
    pixel_access = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixel_access[x, y]
            if red >= threshold and green >= threshold and blue >= threshold:
                pixel_access[x, y] = (red, green, blue, 0)
    return rgba


def _fit_square(image: Image.Image, size: int = 1024, padding_ratio: float = 0.12) -> Image.Image:
    trimmed = _remove_near_white_background(image)
    bbox = trimmed.getbbox()
    if bbox is None:
        raise ValueError("The icon source became empty after background cleanup.")
    cropped = trimmed.crop(bbox)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner_size = max(1, int(size * (1.0 - (padding_ratio * 2))))
    fitted = cropped.copy()
    fitted.thumbnail((inner_size, inner_size), Image.Resampling.LANCZOS)
    offset = ((size - fitted.width) // 2, (size - fitted.height) // 2)
    canvas.alpha_composite(fitted, offset)
    return canvas


def main() -> int:
    source_path = _find_source()
    base_icon = _fit_square(Image.open(source_path))
    icon_512 = base_icon.resize((512, 512), Image.Resampling.LANCZOS)
    icon_180 = base_icon.resize((180, 180), Image.Resampling.LANCZOS)
    icon_1024 = base_icon.resize((1024, 1024), Image.Resampling.LANCZOS)

    OUTPUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_ICNS.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DESKTOP_PNG.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_WEB_PNG.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_APPLE_PNG.parent.mkdir(parents=True, exist_ok=True)

    icon_512.save(OUTPUT_DESKTOP_PNG, format="PNG", optimize=True)
    icon_512.save(OUTPUT_WEB_PNG, format="PNG", optimize=True)
    icon_180.save(OUTPUT_APPLE_PNG, format="PNG", optimize=True)
    icon_1024.save(OUTPUT_ICNS, format="ICNS")
    base_icon.save(
        OUTPUT_ICO,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"Generated app icons from {source_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
