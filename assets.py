# assets.py
# Step 10: copy the pictures from the original page into the output folder.
# The pictures still belong to the original website: keep them for personal learning.

import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# A normal browser name, because some sites refuse requests that look automated.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# Safety limits: no slow requests, no gigantic files.
TIMEOUT = 15
MAX_BYTES = 5 * 1024 * 1024

# The picture types we understand, and the file ending to use for each one.
CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
}

URL_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif")


def ending_from_url(src):
    """Guess the file ending from the address, or return None if it is unclear."""
    ending = Path(urlparse(src).path).suffix.lower()

    if ending == ".jpeg":
        return ".jpg"
    if ending in URL_ENDINGS:
        return ending

    return None


def download_one(src, target):
    """Download one picture to target. Returns the file ending used, or None."""
    request = urllib.request.Request(src, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = (response.headers.get("Content-Type") or "")
        content_type = content_type.split(";")[0].strip().lower()

        # The server's answer is more reliable than the address, but try both.
        ending = CONTENT_TYPES.get(content_type) or ending_from_url(src)
        if ending is None:
            return None

        data = response.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            return None

        path = target.with_suffix(ending)
        path.write_bytes(data)
        return ending


def download_images(images, folder, limit=8):
    """Save up to `limit` pictures into folder. Returns the ones that worked."""
    folder.mkdir(parents=True, exist_ok=True)
    saved = []

    for image in images:
        if len(saved) >= limit:
            break

        src = image.get("src", "")
        if not src.startswith(("http://", "https://")):
            continue

        # image-01, image-02, ... The ending is added once we know the type.
        target = folder / f"image-{len(saved) + 1:02d}"

        try:
            ending = download_one(src, target)
        except Exception:
            continue        # a broken or forbidden picture must not stop the rest

        if ending is None:
            continue

        saved.append(
            {
                "path": "images/" + target.with_suffix(ending).name,
                "alt": image.get("alt", ""),
            }
        )

    return saved
