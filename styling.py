# styling.py
# Step 8: turn the palette into a style.css file.
# The colours come from the original page; the layout rules are ours.

from string import Template

# Every colour variable, with the comment that explains it.
# (name, comment) pairs, in the order they appear in the file.
VARIABLES = [
    ("background", "page background"),
    ("text", "normal writing"),
    ("accent", "strong colour: header band"),
    ("accent-text", "writing on top of the accent"),
    ("link", "links"),
    ("panel", "faint tint for the footer"),
    ("line", "thin dividing lines"),
]

# The dark version overrides these variables (the button adds class="dark" to body).
DARK_VARIABLES = ["background", "text", "link", "panel", "line"]

# name -> comment, so both blocks stay described the same way.
COMMENTS = dict(VARIABLES)

# The stylesheet. $root is replaced by the :root block built below.
# The rest of the file uses var(--name), so a colour only lives in one place.
CSS_TEMPLATE = Template(
    """/* style.css
   Built from the colours of the original page.
   All the colours live in :root below: change one and the page follows. */

$root

/* The same page in the other scheme: the button adds class="dark" to <body>. */
$dark

/* Widths include the padding, so nothing gets wider than we expect. */
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--background);
  color: var(--text);
  font-family: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 17px;
  line-height: 1.65;
}

/* One centred column, shared by the header band, the main text and the footer. */
header,
main,
footer {
  /* The band still reaches both edges, but the writing lines up in the column. */
  padding-left: max(24px, calc((100% - var(--max-width)) / 2));
  padding-right: max(24px, calc((100% - var(--max-width)) / 2));
}

header {
  /* Lets the button sit in the top-right corner of the coloured band. */
  position: relative;
  background: var(--accent);
  color: var(--accent-text);
  padding-top: 64px;
  padding-bottom: 56px;
}

h1 {
  margin: 0 0 14px;
  /* clamp(minimum, preferred, maximum): big on wide screens, smaller on phones. */
  font-size: clamp(32px, 5vw, 46px);
  line-height: 1.15;
  letter-spacing: -0.5px;
}

header p {
  margin: 0;
  max-width: 44em;
  font-size: 20px;
  opacity: 0.9;              /* slightly softer than the title */
}

/* The small button that switches the page between light and dark. */
#theme-toggle {
  position: absolute;
  top: 24px;
  right: max(24px, calc((100% - var(--max-width)) / 2));
  padding: 8px 16px;
  border: 1px solid currentColor;
  border-radius: 999px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

#theme-toggle:hover {
  opacity: 0.7;
}

main {
  padding-top: 8px;
  padding-bottom: 48px;
}

/* Pictures copied from the original page, as a row of tidy cards. */
.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  padding: 10px 0 28px;
}

.gallery img {
  width: 100%;
  height: 160px;
  object-fit: contain;       /* show the whole picture, never crop it */
  padding: 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
}

section {
  padding: 30px 0;
  border-bottom: 1px solid var(--line);
}

/* The last section does not need a line under it. */
section:last-child {
  border-bottom: none;
}

h2 {
  margin: 0 0 10px;
  font-size: 26px;
  line-height: 1.25;
}

p {
  margin: 0 0 12px;
}

a {
  color: var(--link);
  text-decoration: none;
  border-bottom: 1px solid currentColor;
}

a:hover {
  opacity: 0.75;
}

footer {
  background: var(--panel);
  padding-top: 26px;
  padding-bottom: 26px;
  font-size: 14px;
}

footer p {
  margin: 0;
  opacity: 0.7;
}
"""
)


def hex_to_rgb(colour):
    """Turn '#2b5b84' into (43, 91, 132). Returns None if it is not a hex colour."""
    text = str(colour).strip().lstrip("#")

    if len(text) == 3:                     # '#abc' means '#aabbcc'
        text = text[0] * 2 + text[1] * 2 + text[2] * 2

    if len(text) != 6:
        return None

    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return None


def pick(colour, fallback):
    """Use the colour if it is a real hex value, otherwise the fallback."""
    if hex_to_rgb(colour):
        return str(colour).strip().upper()
    return fallback


def mix(first, second, amount):
    """Blend two hex colours. amount 0 gives the first, 1 gives the second."""
    one = hex_to_rgb(first)
    two = hex_to_rgb(second)

    if not one or not two:
        return first

    parts = []
    for index in range(3):
        value = round(one[index] + (two[index] - one[index]) * amount)
        parts.append(f"{value:02X}")

    return "#" + "".join(parts)


def brightness(colour):
    """How light a colour is, from 0 (black) to 255 (white)."""
    red, green, blue = hex_to_rgb(colour) or (255, 255, 255)
    return round(0.299 * red + 0.587 * green + 0.114 * blue)


def relative_luminance(colour):
    """How much light a colour gives off, from 0 (black) to 1 (white)."""
    parts = []

    for value in hex_to_rgb(colour) or (0, 0, 0):
        part = value / 255

        if part <= 0.03928:
            parts.append(part / 12.92)
        else:
            parts.append(((part + 0.055) / 1.055) ** 2.4)

    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def contrast(first, second):
    """Contrast ratio of two colours. 4.5 or more is comfortable to read."""
    one = relative_luminance(first)
    two = relative_luminance(second)
    lighter = max(one, two)
    darker = min(one, two)

    return round((lighter + 0.05) / (darker + 0.05), 2)


def readable_on(colour):
    """Black or white writing, whichever is easier to read on this colour."""
    if brightness(colour) < 140:
        return "#FFFFFF"
    return "#111111"


def root_block(values):
    """Build the :root block, with every comment lined up in one column."""
    lines = [":root {"]

    for name, comment in VARIABLES:
        # ljust pads with spaces until the text is that many characters wide.
        label = ("--" + name + ":").ljust(16)
        value = (values[name] + ";").ljust(9)
        lines.append("  " + label + value + "/* " + comment + " */")

    lines.append("  --max-width:   1000px;   /* widest the column ever gets */")
    lines.append("}")
    return "\n".join(lines)


def dark_values(values):
    """Colours for the other scheme: light writing on a dark page, or the reverse."""
    background = values["background"]
    text = values["text"]

    # Move 88% of the way from this background to the text colour.
    other_background = mix(background, text, 0.88)
    other_text = readable_on(other_background)

    link = values["link"]
    if contrast(link, other_background) < 3:
        link = mix(link, other_text, 0.55)
    if contrast(link, other_background) < 3:
        link = other_text

    return {
        "background": other_background,
        "text": other_text,
        "link": link,
        "panel": mix(other_background, other_text, 0.06),
        "line": mix(other_background, other_text, 0.16),
    }


def dark_block(values):
    """Build the body.dark block that swaps the colours when the button is used."""
    lines = ["body.dark {"]

    for name in DARK_VARIABLES:
        label = ("--" + name + ":").ljust(16)
        value = (values[name] + ";").ljust(9)
        lines.append("  " + label + value + "/* " + COMMENTS[name] + " */")

    lines.append("}")
    return "\n".join(lines)


def build_css(palette=None):
    """Return the whole stylesheet as one string."""
    palette = palette or {}

    background = pick(palette.get("background"), "#FFFFFF")
    text = pick(palette.get("text"), "#111111")
    accent = pick(palette.get("accent"), text)
    link = pick(palette.get("link"), accent)

    # A link the same lightness as the page is almost invisible.
    # Fall back to the accent, then to the normal text colour.
    if contrast(link, background) < 3:
        link = accent
    if contrast(link, background) < 3:
        link = text

    values = {
        "background": background,
        "text": text,
        "accent": accent,
        "accent-text": readable_on(accent),
        "link": link,
        "panel": mix(background, text, 0.04),   # 4% of the text colour in the background
        "line": mix(background, text, 0.12),    # a little stronger, for lines
    }

    other = dark_values(values)

    return CSS_TEMPLATE.substitute(root=root_block(values), dark=dark_block(other))
