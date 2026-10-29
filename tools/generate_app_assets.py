from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CANDIDATES = (
    PROJECT_ROOT / "logo.png",
    PROJECT_ROOT / "assets" / "app logo.png",
)
ICON_OUTPUT = PROJECT_ROOT / "assets" / "icon.ico"
FAVICON_OUTPUT = PROJECT_ROOT / "client" / "public" / "favicon.png"
APP_ICON_192_OUTPUT = PROJECT_ROOT / "client" / "public" / "app-icon-192.png"
APP_ICON_512_OUTPUT = PROJECT_ROOT / "client" / "public" / "app-icon-512.png"

BACKGROUND_THRESHOLD = 242


def _pick_source() -> Path:
    for candidate in SOURCE_CANDIDATES:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path) for path in SOURCE_CANDIDATES)
    raise FileNotFoundError(f"Could not find a source logo image. Looked for: {searched}")


def _is_background(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    return a > 0 and r >= BACKGROUND_THRESHOLD and g >= BACKGROUND_THRESHOLD and b >= BACKGROUND_THRESHOLD


def _strip_edge_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    queue: deque[tuple[int, int]] = deque()
    visited: set[tuple[int, int]] = set()

    def push(x: int, y: int) -> None:
        if (x, y) in visited:
            return
        if not _is_background(pixels[x, y]):
            return
        visited.add((x, y))
        queue.append((x, y))

    for x in range(width):
        push(x, 0)
        push(x, height - 1)
    for y in range(height):
        push(0, y)
        push(width - 1, y)

    while queue:
        x, y = queue.popleft()
        pixels[x, y] = (255, 255, 255, 0)
        if x > 0:
            push(x - 1, y)
        if x < width - 1:
            push(x + 1, y)
        if y > 0:
            push(x, y - 1)
        if y < height - 1:
            push(x, y + 1)

    return rgba


def _render_square_icon(image: Image.Image, size: int, padding_ratio: float = 0.1) -> Image.Image:
    processed = _strip_edge_background(image)
    bbox = processed.getbbox()
    if bbox:
        processed = processed.crop(bbox)

    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    inner_size = max(1, int(size * (1 - (padding_ratio * 2))))
    processed.thumbnail((inner_size, inner_size), Image.Resampling.LANCZOS)
    offset = ((size - processed.width) // 2, (size - processed.height) // 2)
    canvas.alpha_composite(processed, offset)
    return canvas


def main() -> int:
    source = _pick_source()
    source_image = Image.open(source)

    ICON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FAVICON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    icon_512 = _render_square_icon(source_image, 512)
    icon_192 = _render_square_icon(source_image, 192)
    favicon = _render_square_icon(source_image, 64, padding_ratio=0.12)
    ico_base = _render_square_icon(source_image, 256)

    icon_512.save(APP_ICON_512_OUTPUT, format="PNG")
    icon_192.save(APP_ICON_192_OUTPUT, format="PNG")
    favicon.save(FAVICON_OUTPUT, format="PNG")
    ico_base.save(
        ICON_OUTPUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"Generated icon assets from {source}")
    print(f" - {ICON_OUTPUT}")
    print(f" - {FAVICON_OUTPUT}")
    print(f" - {APP_ICON_192_OUTPUT}")
    print(f" - {APP_ICON_512_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
