# analyse.py
# Step 5: turn the raw page data into a clean summary we can build from.

import re

# Words that usually mean "this is site furniture, not content".
NOISE_PHRASES = (
    "cookie",
    "accept all",
    "consent",
    "skip to",
    "sign in",
    "sign up",
    "log in",
    "log out",
    "subscribe",
    "newsletter",
    "privacy policy",
    "terms of use",
    "terms and conditions",
    "all rights reserved",
    "copyright",
    "javascript",
    "your browser",
    "advertisement",
    "follow us",
    "share this",
    "share on",
    "back to top",
    "download the app",
    "search",
    "menu",
    "toggle navigation",
    "sponsored",
    "interactive scripts",
)

# Used when the page gives us no background colour at all.
DEFAULT_BACKGROUND = "#FFFFFF"


def is_noise(text):
    """True if this text looks like boilerplate instead of page content."""
    lower = text.lower()

    if len(lower.strip()) < 3:
        return True

    for phrase in NOISE_PHRASES:
        if phrase in lower:
            return True

    return False


def rgb_to_hex(colour):
    """Turn 'rgb(43, 91, 132)' into '#2B5B84'. Anything else is returned as-is."""
    numbers = re.findall(r"\d+", colour)

    if len(numbers) < 3:
        return colour.upper()

    red = int(numbers[0])
    green = int(numbers[1])
    blue = int(numbers[2])

    return f"#{red:02X}{green:02X}{blue:02X}"


def heading_level(tag):
    """'h2' becomes 2. Anything strange becomes 0."""
    if len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
        return int(tag[1])
    return 0


def clean_headings(headings):
    """Drop boilerplate and repeats, then put the headings in visual order."""
    ordered = sorted(headings, key=lambda item: item.get("top", 0))

    cleaned = []
    seen = []

    for item in ordered:
        text = item.get("text", "").strip()

        if not text or is_noise(text):
            continue

        key = text.lower()
        if key in seen:
            continue

        seen.append(key)
        cleaned.append(
            {
                "tag": item.get("tag", ""),
                "level": heading_level(item.get("tag", "")),
                "text": text,
                "top": item.get("top", 0),
            }
        )

    return cleaned


def clean_paragraphs(paragraphs):
    """Drop boilerplate and repeats from the body text."""
    cleaned = []
    seen = []

    for text in paragraphs:
        if is_noise(text):
            continue

        key = text.lower()
        if key in seen:
            continue

        seen.append(key)
        cleaned.append(text)

    return cleaned


def clean_images(images):
    """Drop duplicates, embedded blobs and invisible tracking pixels."""
    cleaned = []
    seen = []

    for image in images:
        src = image.get("src", "")

        if not src or src in seen:
            continue

        if src.startswith("data:"):
            continue

        if "1x1" in src or "pixel" in src.lower():
            continue

        seen.append(src)
        cleaned.append({"src": src, "alt": image.get("alt", "")})

    return cleaned


def colour_for(colours, role, part):
    """Find the colour used by one role, e.g. the body's background."""
    for item in colours:
        if item.get("role") == role:
            value = item.get(part, "")
            if value:
                return rgb_to_hex(value)

    return ""


def colour_counts(colours):
    """List every colour we saw and where it was used, e.g. '#2B5B84': ['header bg']."""
    counts = {}

    for item in colours:
        role = item.get("role", "?")

        for part in ("text", "background"):
            value = item.get(part, "")
            if not value:
                continue

            hex_value = rgb_to_hex(value)
            label = role + (" text" if part == "text" else " bg")

            labels = counts.setdefault(hex_value, [])
            if label not in labels:
                labels.append(label)

    return counts


def build_palette(colours):
    """Pick the four colours a rebuild needs most."""
    background = colour_for(colours, "body", "background")

    if not background:
        for item in colours:
            if item.get("background"):
                background = rgb_to_hex(item["background"])
                break

    if not background:
        background = DEFAULT_BACKGROUND

    text = colour_for(colours, "body", "text") or colour_for(colours, "p", "text") or "#000000"

    link = colour_for(colours, "a", "text")

    accent = colour_for(colours, "button", "background")
    if not accent:
        accent = colour_for(colours, "header", "background")
    if not accent:
        accent = link or text

    return {
        "background": background,
        "text": text,
        "accent": accent,
        "link": link,
        "seen": colour_counts(colours),
    }


def summarise(data):
    """Turn one raw page dictionary into the clean summary we build from later."""
    headings = clean_headings(data.get("headings", []))

    return {
        "source": data.get("address", ""),
        "title": data.get("title", ""),
        "main_heading": headings[0]["text"] if headings else "",
        "headings": headings,
        "paragraphs": clean_paragraphs(data.get("paragraphs", [])),
        "images": clean_images(data.get("images", [])),
        "palette": build_palette(data.get("colours", [])),
    }
