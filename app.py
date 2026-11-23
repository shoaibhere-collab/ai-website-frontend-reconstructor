# app.py
# Step 4: read the page's headings, text, images and colours and save what we find.

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

import analyse
import ai
import assets
import build
import preview
import reconstruct
import scripting
import styling

# Show the browser window while it works. Change to True to run invisibly.
HEADLESS = False

# Where the screenshot and the page details are saved.
SCREENSHOT_DIR = Path("screenshots")
DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")

# Limits, so a huge page cannot create a gigantic file.
MAX_HEADINGS = 40
MAX_PARAGRAPHS = 30
MAX_IMAGES = 40

# The kinds of elements whose colours tell us the look of the page.
# "html" comes first because many pages paint the background there, not on body.
COLOUR_SELECTORS = ["html", "body", "header", "nav", "main", "h1", "h2", "p", "a", "button"]


def clean_url(raw_url):
    """Turn whatever the user typed into an address starting with https://."""
    url = raw_url.strip()

    if "://" not in url:
        url = "https://" + url

    return url


def find_url_problem(url):
    """Return a short sentence explaining the problem, or None if the URL is fine."""
    if url == "https://":
        return "You did not type anything."

    if " " in url:
        return "A website address cannot contain spaces."

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return "Only http:// and https:// addresses are supported."

    if not parsed.netloc:
        return "The address is missing a domain name, like example.com."

    if "." not in parsed.netloc:
        return "The domain name looks incomplete. Example: example.com"

    return None


def domain_name(url):
    """Return the site name without www, e.g. news.bbc.co.uk."""
    return urlparse(url).netloc.replace("www.", "")


def safe_file_name(url):
    """Turn the domain into a name Windows accepts as a file name."""
    name = domain_name(url)
    return re.sub(r"[^a-zA-Z0-9.-]", "_", name)


def screenshot_path_for(url):
    """Build a path like screenshots/example.com.png."""
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    return SCREENSHOT_DIR / f"{safe_file_name(url)}.png"


def data_path_for(url):
    """Build a path like data/example.com.json."""
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"{safe_file_name(url)}.json"


def summary_path_for(url):
    """Build a path like data/example.com.summary.json."""
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"{safe_file_name(url)}.summary.json"


def plan_path_for(url):
    """Build a path like data/example.com.plan.json."""
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"{safe_file_name(url)}.plan.json"


def output_folder_for(url):
    """Build a folder like output/example.com/ for the rebuilt site."""
    folder = OUTPUT_DIR / safe_file_name(url)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def html_path_for(url):
    """Build a path like output/example.com/index.html."""
    return output_folder_for(url) / "index.html"


def css_path_for(url):
    """Build a path like output/example.com/style.css."""
    return output_folder_for(url) / "style.css"


def js_path_for(url):
    """Build a path like output/example.com/script.js."""
    return output_folder_for(url) / "script.js"


def images_folder_for(url):
    """Build a folder like output/example.com/images/."""
    folder = output_folder_for(url) / "images"
    folder.mkdir(exist_ok=True)
    return folder


def tidy(text):
    """Squash runs of spaces, tabs and newlines into single spaces."""
    return " ".join(text.split())


def ascii_safe(text):
    """Text that is safe to print in a Windows terminal."""
    return text.encode("ascii", "replace").decode("ascii")


def collect_headings(page):
    """Find every h1, h2 and h3, and record where each one sits on the page."""
    headings = []

    for element in page.query_selector_all("h1, h2, h3"):
        text = tidy(element.inner_text())
        if not text:
            continue

        details = element.evaluate(
            """el => {
                const r = el.getBoundingClientRect();
                return { tag: el.tagName.toLowerCase(), top: Math.round(r.top + window.scrollY) };
            }"""
        )
        headings.append({"tag": details["tag"], "text": text, "top": details["top"]})

        if len(headings) >= MAX_HEADINGS:
            break

    return headings


def collect_paragraphs(page):
    """Find the visible paragraphs of body text, in the page's own language."""
    paragraphs = []
    page_language = page.evaluate("() => document.documentElement.lang || ''")

    for element in page.query_selector_all("p"):
        text = tidy(element.inner_text())
        if len(text) < 20:          # tiny or empty paragraphs are not useful
            continue

        # A paragraph can say which language it is in, like <p lang="ar">.
        language = element.evaluate(
            "el => (el.closest('[lang]') || document.documentElement).lang || ''"
        )

        # "en-GB" and "en" are the same language for our purpose.
        if page_language and language:
            if language.split("-")[0].lower() != page_language.split("-")[0].lower():
                continue

        paragraphs.append(text)

        if len(paragraphs) >= MAX_PARAGRAPHS:
            break

    return paragraphs


def collect_images(page):
    """Find the images, with their full address and alt text."""
    images = []
    seen = []

    for element in page.query_selector_all("img"):
        # currentSrc is the picture the browser really chose, and it is already
        # a full address. src is the plain fallback when there is only one file.
        src = element.evaluate("el => el.currentSrc || el.src")
        if not src or src in seen:
            continue

        alt = element.get_attribute("alt") or ""
        images.append({"src": src, "alt": tidy(alt)})
        seen.append(src)

        if len(images) >= MAX_IMAGES:
            break

    return images


def collect_colours(page):
    """Ask the browser for the text and background colour of key elements."""
    colours = []
    seen = []

    for selector in COLOUR_SELECTORS:
        element = page.query_selector(selector)
        if element is None:
            continue

        style = element.evaluate(
            """el => {
                const s = getComputedStyle(el);
                return { color: s.color, background: s.backgroundColor };
            }"""
        )

        background = style["background"]
        if background == "rgba(0, 0, 0, 0)":    # transparent: nothing to learn
            background = ""

        key = (selector, style["color"], background)
        if key in seen:
            continue

        colours.append(
            {"role": selector, "text": style["color"], "background": background}
        )
        seen.append(key)

    return colours


def load_lazy_images(page):
    """Scroll to the bottom and back, so lazily loaded pictures really appear."""
    page.evaluate(
        """async () => {
            const pause = ms => new Promise(done => setTimeout(done, ms));
            const step = window.innerHeight;

            // The page gets taller as pictures arrive, so check the height each
            // time. The step limit stops endless pages from scrolling forever.
            let steps = 0;
            for (let y = 0; y < document.body.scrollHeight && steps < 60; y += step) {
                window.scrollTo(0, y);
                steps += 1;
                await pause(100);
            }

            window.scrollTo(0, 0);
            await pause(300);
        }"""
    )


def collect_page_data(page, url):
    """Gather everything into one dictionary we can save as JSON."""
    return {
        "address": page.url,
        "title": tidy(page.title()),
        "headings": collect_headings(page),
        "paragraphs": collect_paragraphs(page),
        "images": collect_images(page),
        "colours": collect_colours(page),
    }


def write_json(path, data):
    """Write a dictionary to a .json file."""
    # encoding="utf-8" keeps letters from any language readable.
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    return path


def save_data(url, data):
    """Save the raw findings from Step 4."""
    return write_json(data_path_for(url), data)


def save_summary(url, summary):
    """Save the clean summary from Step 5."""
    return write_json(summary_path_for(url), summary)


def save_plan(url, plan):
    """Save the page plan from Step 6."""
    return write_json(plan_path_for(url), plan)


def save_html(url, html_text):
    """Save the rebuilt page as index.html inside its own folder."""
    path = html_path_for(url)
    path.write_text(html_text, encoding="utf-8")
    return path


def save_css(url, css_text):
    """Save the stylesheet next to the page, so index.html can find it."""
    path = css_path_for(url)
    path.write_text(css_text, encoding="utf-8")
    return path


def save_js(url, js_text):
    """Save the script next to the page, so the button can work."""
    path = js_path_for(url)
    path.write_text(js_text, encoding="utf-8")
    return path


def build_editable_site(data, summary, plan, url, folder):
    """Write the editable project (HTML, CSS, JS and assets) into folder.

    reconstruct.py does the real work: it turns the structure that was read in
    the browser into ordinary HTML elements and a stylesheet. If that fails for
    some reason, the older template is used, so a run never ends with nothing.
    """
    structure = data.get("structure") or {}

    try:
        return reconstruct.build_site(
            structure,
            folder,
            data.get("address") or url,
            screenshot=screenshot_reference_for(url),
        )
    except Exception as error:
        print("\n[!] The page structure could not be rebuilt:", ascii_safe(str(error)))
        print("    Falling back to the simple template.")

    images = assets.download_images(summary.get("images", []), images_folder_for(url))
    html_text = build.build_html(
        plan, summary.get("palette", {}), summary.get("source", ""), images
    )
    css_text = styling.build_css(summary.get("palette", {}))
    js_text = scripting.build_js()

    html_file = save_html(url, html_text)
    css_file = save_css(url, css_text)
    js_file = save_js(url, js_text)

    return {
        "folder": folder,
        "html": html_text,
        "css": css_text,
        "js": js_text,
        "html_file": html_file,
        "css_file": css_file,
        "js_file": js_file,
        "assets": [folder / image["path"] for image in images],
        "reference": None,
        "elements": 0,
    }


def screenshot_reference_for(url):
    """The reference picture, if this run made one."""
    path = screenshot_path_for(url)
    return path if path.exists() else None


def visit_page(url):
    """Open the url, save a screenshot, read the page. Returns a dict or None."""
    file_path = screenshot_path_for(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        # A normal laptop screen size, so the page looks like it would for a visitor.
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        try:
            # "load" waits for every picture and advert, which some sites never
            # finish; the short pause below is what actually gives the page time.
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError as error:
            browser.close()
            print("\n[x] The browser could not load that page.")
            print("    Details:", str(error).splitlines()[0])
            print("    Check the address, your internet connection, or try another site.")
            return None

        # Give images, fonts and animations a moment to finish.
        page.wait_for_timeout(1500)

        # Pictures marked "lazy" only load when they get near the screen,
        # so scroll through the page once before reading it.
        load_lazy_images(page)

        print("\n[ok] Page title   :", ascii_safe(page.title()))
        print("[ok] Final address:", page.url)
        if response is not None:
            print("[ok] Server answer:", response.status)

        # full_page=True captures the whole page, not just the visible part.
        # This picture is kept only as a reference to compare the rebuild with.
        page.screenshot(path=str(file_path), full_page=True)

        data = collect_page_data(page, url)

        # Read the whole visible structure - sections, navigation, cards, lists,
        # buttons, pictures - so the rebuild is real HTML and CSS, not an image.
        data["structure"] = reconstruct.extract(page)

        browser.close()

    if not file_path.exists():
        print("\n[x] The page loaded but no screenshot file was created.")

    return {"screenshot": file_path, "data": data}


def print_report(summary):
    """Show the clean summary in the terminal."""
    print("\n--- Clean summary ---")
    print("Title    :", ascii_safe(summary["title"]))

    print("Headings :", len(summary["headings"]), "(in visual order)")
    for heading in summary["headings"][:8]:
        print("    h" + str(heading["level"]), "|", ascii_safe(heading["text"])[:70])

    print("Paragraphs:", len(summary["paragraphs"]))
    if summary["paragraphs"]:
        print("    first:", ascii_safe(summary["paragraphs"][0])[:90])

    print("Images   :", len(summary["images"]))

    palette = summary["palette"]
    print("Palette  :")
    print("    background", palette["background"])
    print("    text      ", palette["text"])
    print("    accent    ", palette["accent"])
    print("    link      ", palette["link"])


def print_plan(plan):
    """Show the page plan in the terminal."""
    print("\n--- Page plan (" + plan.get("mode", "?") + ") ---")
    print("Title    :", ascii_safe(plan["title"]))
    print("Tagline  :", ascii_safe(plan["tagline"])[:100])

    for section in plan["sections"]:
        print("  Section:", ascii_safe(section["heading"])[:60])
        print("      ", ascii_safe(section["body"])[:100])

    print("Note     :", ascii_safe(plan.get("note", ""))[:100])


def main():
    print("=" * 45)
    print("  Website Frontend Reconstructor")
    print("=" * 45)
    print("Paste a website address, for example: https://example.com")

    raw_url = input("\nWebsite URL: ")
    url = clean_url(raw_url)
    problem = find_url_problem(url)

    if problem:
        print("\n[x] That does not look like a valid website address.")
        print("    Reason:", problem)
        print("    Try again, for example: https://example.com")
        return

    print("\nOpening", url, "in a real browser...")
    print("(The browser window may take a few seconds to appear.)")

    result = visit_page(url)

    if result is None:
        return

    summary = analyse.summarise(result["data"])
    print_report(summary)

    plan = ai.make_plan(summary)
    print_plan(plan)

    folder = output_folder_for(url)
    site = build_editable_site(result["data"], summary, plan, url, folder)

    data_file = save_data(url, result["data"])
    summary_file = save_summary(url, summary)
    plan_file = save_plan(url, plan)

    print("\n[ok] Editable project saved in:", folder.resolve())
    print("      index.html          page structure, real HTML elements")
    print("      style.css           layout, spacing, colours, type")
    print("      script.js           the interactions on the page")
    print("      assets/images/     ", len(site["assets"]), "pictures, used where they belong")
    if site.get("reference"):
        print("      reference/screenshot.png  only to compare the rebuild with")

    print("\n[ok] Notes kept outside the project:")
    print("    ", data_file.resolve())
    print("    ", summary_file.resolve())
    print("    ", plan_file.resolve())

    address = preview.open_page(site["html_file"])
    print("\n[ok] Opening the rebuilt page in your browser:")
    print("    ", address)
    print("     (If nothing appears, copy that address into your browser.)")


if __name__ == "__main__":
    main()
