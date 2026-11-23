# build.py
# Step 7: turn the page plan into a real HTML file.
# There is no CSS yet, so the page will look plain until Step 8.

from html import escape

# Every level of nesting in the HTML file is this many spaces.
INDENT = "  "


def escape_text(text):
    """Make text safe for HTML: < becomes &lt;, & becomes &amp;, and so on."""
    return escape(str(text), quote=True)


def palette_comments(palette, source):
    """Write the original colours and address into the file as comments."""
    lines = [INDENT + "<!-- Colours taken from the original page (see style.css). -->"]

    for name in ("background", "text", "accent", "link"):
        value = palette.get(name, "")
        if value:
            lines.append(INDENT + "<!-- " + name + ": " + escape_text(value) + " -->")

    if source:
        lines.append(INDENT + "<!-- Rebuilt from: " + escape_text(source) + " -->")

    return lines


def build_section(section):
    """Build one <section> block with an h2 heading and a paragraph."""
    heading = escape_text(section.get("heading", ""))
    body = escape_text(section.get("body", ""))

    lines = [
        INDENT * 2 + "<section>",
        INDENT * 3 + "<h2>" + heading + "</h2>",
    ]

    if body:
        lines.append(INDENT * 3 + "<p>" + body + "</p>")

    lines.append(INDENT * 2 + "</section>")
    return lines


def build_gallery(images):
    """Build the strip of pictures copied from the original page."""
    lines = [INDENT + '<div class="gallery">']

    for image in images:
        src = escape_text(image.get("path", ""))
        alt = escape_text(image.get("alt", ""))
        lines.append(INDENT * 2 + '<img src="' + src + '" alt="' + alt + '" loading="lazy">')

    lines.append(INDENT + "</div>")
    return lines


def build_html(plan, palette=None, source="", images=None):
    """Return the whole HTML page as one string."""
    palette = palette or {}
    images = images or []

    title = (plan.get("title") or "").strip() or "Rebuilt page"
    tagline = (plan.get("tagline") or "").strip()

    # Only keep sections that have a heading, so we never build an empty block.
    sections = [item for item in plan.get("sections", []) if item.get("heading")]

    # A page must have something inside <main>, so fall back to the title.
    if not sections:
        sections = [{"heading": title, "body": ""}]

    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        INDENT + '<meta charset="utf-8">',
        INDENT + '<meta name="viewport" content="width=device-width, initial-scale=1">',
        INDENT + "<title>" + escape_text(title) + "</title>",
        INDENT + '<link rel="stylesheet" href="style.css">',
    ]

    lines += palette_comments(palette, source)

    lines += [
        "</head>",
        "<body>",
        INDENT + "<header>",
        INDENT * 2 + "<h1>" + escape_text(title) + "</h1>",
    ]

    if tagline:
        lines.append(INDENT * 2 + "<p>" + escape_text(tagline) + "</p>")

    # The button that script.js listens to.
    lines.append(INDENT * 2 + '<button id="theme-toggle" type="button">Dark mode</button>')

    lines += [
        INDENT + "</header>",
        "",
        INDENT + "<main>",
    ]

    if images:
        lines += build_gallery(images)
        lines.append("")

    for index, section in enumerate(sections):
        if index:                    # a blank line between sections, easier to read
            lines.append("")
        lines += build_section(section)

    lines.append(INDENT + "</main>")

    if source:
        lines += [
            "",
            INDENT + "<footer>",
            INDENT * 2 + "<p>Rebuilt from " + escape_text(source) + "</p>",
            INDENT + "</footer>",
        ]

    # defer means: load the script, but run it after the HTML is ready.
    lines += [
        INDENT + '<script src="script.js" defer></script>',
        "</body>",
        "</html>",
        "",
    ]

    return "\n".join(lines)
