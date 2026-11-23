# streamlit_app.py
# The workspace interface for the Website Frontend Reconstructor.
#
# Only the interface lives here, and its stylesheet is ui.css next to this
# file. The real work is still done by the existing modules: app.py,
# analyse.py, ai.py, build.py, styling.py, scripting.py, assets.py and
# reconstruct.py. None of them are changed by this file.
#
# Run it with:  streamlit run streamlit_app.py

import base64
import io
import json
import re
import time
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st

import ai
import analyse
import app

# The rebuilt page is shown inside this page, so the browser used for
# inspection can stay invisible. This changes the web app only, not app.py.
app.HEADLESS = True

# Pictures larger than this are left out of the on-page preview (they are still
# included in the downloaded files). It keeps the preview quick to render.
MAX_PREVIEW_IMAGE_BYTES = 1_500_000

# The width and height of each preview viewport, in CSS pixels. ui.css keeps
# the same numbers; the frame is scaled down to fit the panel.
DEVICE_HEIGHTS = {"Desktop": 1300, "Tablet": 1000, "Mobile": 680}


# ---------------------------------------------------------------------------
# The look of the interface
# ---------------------------------------------------------------------------
CSS = Path(__file__).with_name("ui.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Small pieces of HTML
# ---------------------------------------------------------------------------
STEPS = ("Address", "Analyse", "Review", "Rebuild", "Preview", "Export")

CHECK_SVG = (
    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">'
    '<path d="M2.6 7.4l3 3 5.8-6.6" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
LINK_SVG = (
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
    '<path d="M6.4 9.6l3.2-3.2M5.3 10.7l-.9.9a2.6 2.6 0 01-3.7-3.7l1.7-1.7a2.6 2.6 0 013.7 0" '
    'stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>'
    '<path d="M10.7 5.3l.9-.9a2.6 2.6 0 013.7 3.7l-1.7 1.7a2.6 2.6 0 01-3.7 0" '
    'stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>'
)
BRAND_SVG = (
    '<svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">'
    '<rect x="1.4" y="1.4" width="15.2" height="15.2" rx="3.2" stroke="currentColor" stroke-width="1.3"/>'
    '<path d="M5.2 12.4V5.6h3.9a2.1 2.1 0 010 4.2H5.2" stroke="currentColor" stroke-width="1.3" '
    'stroke-linejoin="round"/>'
    '<path d="M9.3 9.9l3.2 2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>'
)


def chip(text, kind=""):
    """A small status pill used in panel headers."""
    return '<span class="chip ' + kind + '"><span class="dot"></span>' + escape(text) + "</span>"


def panel_head(title, subtitle="", right=""):
    sub_html = '<p class="p-sub">' + subtitle + "</p>" if subtitle else ""
    st.markdown(
        '<div class="p-head"><div><p class="p-title">'
        + escape(title)
        + "</p>"
        + sub_html
        + "</div>"
        + right
        + "</div>",
        unsafe_allow_html=True,
    )


def stepper(current):
    parts = []

    for index, label in enumerate(STEPS):
        if index < current:
            state, mark = "done", "✓"
        elif index == current:
            state, mark = "current", str(index + 1).zfill(2)
        else:
            state, mark = "", str(index + 1).zfill(2)

        parts.append(
            '<div class="step ' + state + '">'
            '<span class="n">' + mark + "</span>"
            '<span class="t">' + escape(label) + "</span></div>"
        )

        if index < len(STEPS) - 1:
            parts.append('<div class="step-sep"></div>')

    st.markdown('<div class="stepper">' + "".join(parts) + "</div>", unsafe_allow_html=True)


def metric_strip(items):
    cells = []

    for label, value in items:
        cells.append(
            '<div class="metric"><span class="m-k">'
            + escape(label)
            + '</span><span class="m-v">'
            + escape(str(value))
            + "</span></div>"
        )

    st.markdown('<div class="metrics">' + "".join(cells) + "</div>", unsafe_allow_html=True)


def draw_progress(box, headline, stages, active):
    rows = []

    for index, label in enumerate(stages):
        if index < active:
            state, mark = "done", CHECK_SVG
        elif index == active:
            state, mark = "active", ""
        else:
            state, mark = "", ""

        rows.append(
            '<li class="stage ' + state + '">'
            '<span class="mark">' + mark + "</span>"
            "<span>" + escape(label) + "</span></li>"
        )

    box.markdown(
        '<div class="progress">'
        '<div class="live"><span class="dot"></span><span>'
        + escape(headline)
        + '</span></div>'
        '<div class="bar"><span></span></div>'
        '<ul class="stages">' + "".join(rows) + "</ul>"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Reading what the last run left on disk
# ---------------------------------------------------------------------------
def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recent_projects(limit=6):
    """The output folders that already hold a rebuilt page, newest first."""
    if not app.OUTPUT_DIR.exists():
        return []

    found = []

    for folder in app.OUTPUT_DIR.iterdir():
        page = folder / "index.html"

        if folder.is_dir() and page.exists():
            found.append((folder.name, page.stat().st_mtime))

    found.sort(key=lambda item: item[1], reverse=True)
    return [name for name, _ in found[:limit]]


def size_label(size):
    if size >= 1024 * 1024:
        return str(round(size / (1024 * 1024), 1)) + " MB"
    if size >= 1024:
        return str(round(size / 1024)) + " KB"
    return str(size) + " B"


def output_rows(folder):
    root = Path(folder)
    rows = []

    for name in ("index.html", "style.css", "script.js"):
        path = root / name
        if path.exists():
            rows.append((name, size_label(path.stat().st_size)))

    images = root / "assets" / "images"
    if images.exists():
        count = len([item for item in images.iterdir() if item.is_file()])
        rows.append(("assets/images/", str(count) + " files"))

    if (root / "reference" / "screenshot.png").exists():
        rows.append(("reference/", "screenshot"))

    return rows


def reference_path(folder, url):
    inside = Path(folder) / "reference" / "screenshot.png"
    if inside.exists():
        return inside

    outside = app.screenshot_path_for(url)
    return outside if outside.exists() else None


def structure_of(analysis):
    return (analysis.get("data") or {}).get("structure") or {}


def design_tokens(palette, structure):
    body = structure.get("body") or {}
    seen = list((palette.get("seen") or {}).keys())
    tokens = {
        "colour": {
            "background": palette.get("background"),
            "text": palette.get("text"),
            "accent": palette.get("accent"),
            "link": palette.get("link"),
            "extracted": seen[:12],
        },
        "type": {
            "family": body.get("fontFamily"),
            "size": str(body.get("size")) + "px" if body.get("size") else None,
            "lineHeight": body.get("lineHeight"),
        },
    }
    return json.dumps(tokens, indent=2, ensure_ascii=False)


def figma_readme(title, url):
    return (
        "# Figma handoff\n\n"
        "Source: " + url + "\n"
        "Page: " + (title or "Untitled") + "\n"
        "Exported: " + datetime.now().strftime("%d %B %Y, %H:%M") + "\n\n"
        "This bundle is the rebuilt page as editable code and image files. "
        "It is not a screenshot.\n\n"
        "## How to bring it into Figma\n\n"
        "1. Unzip the bundle and open `index.html` in a browser to check the page.\n"
        "2. Import that page with an HTML-to-Figma importer (a plugin that reads a "
        "local or hosted HTML page). Frames, text and images arrive as editable layers.\n"
        "3. Install any missing fonts locally, or map them to fonts in your Figma library.\n"
        "4. Images live in `assets/images/` and are linked relatively, so keep the folder "
        "structure together.\n\n"
        "## Notes\n\n"
        "- Layout and colour come from the original page's computed styles.\n"
        "- Hidden menus and the mobile navigation are separate layers. Duplicate the "
        "frame for each breakpoint to show their open states.\n"
        "- The original full-page screenshot is in `reference/` if it was captured.\n"
    )


def bundle_bytes(folder, readme=""):
    buffer = io.BytesIO()
    root = Path(folder)

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())

        if readme:
            archive.writestr("FIGMA.md", readme)

    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Session actions
# ---------------------------------------------------------------------------
def start_over():
    """Clear the session before the page is drawn again."""
    for key in ("analysis", "result"):
        st.session_state.pop(key, None)

    st.session_state["url_input"] = ""
    st.session_state["device"] = "Desktop"
    st.session_state["view"] = "Rebuilt"


def open_project(name):
    """Show a page that a previous run already saved in the output folder."""
    folder = app.OUTPUT_DIR / name
    page = folder / "index.html"

    if not page.exists():
        return

    summary = read_json(app.DATA_DIR / (name + ".summary.json"))
    data = read_json(app.DATA_DIR / (name + ".json"))
    plan = read_json(app.DATA_DIR / (name + ".plan.json"))

    if not summary and data:
        try:
            summary = analyse.summarise(data)
        except Exception:
            summary = {}

    html_text = read_text(page)
    images_folder = folder / "assets" / "images"
    images = sorted(images_folder.glob("*")) if images_folder.exists() else []

    st.session_state["analysis"] = {
        "url": summary.get("source") or ("https://" + name),
        "summary": summary,
        "data": data,
        "seconds": None,
        "loaded": True,
    }
    st.session_state["result"] = {
        "html": html_text,
        "css": read_text(folder / "style.css"),
        "js": read_text(folder / "script.js"),
        "plan": plan,
        "images": images,
        "pieces": len(re.findall(r"<[a-zA-Z][^>]*>", html_text)),
        "folder": folder,
        "seconds": None,
        "loaded": True,
    }
    st.session_state["url_input"] = st.session_state["analysis"]["url"]
    st.session_state["device"] = "Desktop"
    st.session_state["view"] = "Rebuilt"


def run_analysis(box):
    """Read the page the user typed and keep the result in the session."""
    url = app.clean_url(st.session_state.get("url_input", ""))
    problem = app.find_url_problem(url)

    if problem:
        st.error("That address needs another look. " + problem)
        return False

    stages = [
        "Checking the address",
        "Loading the page in a real browser",
        "Reading structure, copy and images",
    ]
    started = time.perf_counter()
    draw_progress(box, "Opening the page", stages, 1)

    try:
        visited = app.visit_page(url)
    except Exception as error:                      # a missing browser, a crash, ...
        box.empty()
        st.error("The browser could not start. " + str(error))
        return False

    if visited is None:
        box.empty()
        st.error(
            "That page could not be loaded. Check the address or your connection, "
            "then try again."
        )
        return False

    draw_progress(box, "Reading the page", stages, 2)
    summary = analyse.summarise(visited["data"])
    box.empty()

    st.session_state["analysis"] = {
        "url": url,
        "summary": summary,
        "data": visited["data"],
        "seconds": round(time.perf_counter() - started, 1),
        "loaded": False,
    }

    # A new analysis makes any earlier build stale.
    st.session_state.pop("result", None)
    return True


def run_generation(box, analysis):
    """Build the site from the stored analysis and keep the files in the session."""
    url = analysis["url"]
    summary = analysis["summary"]

    stages = [
        "Reading the page structure",
        "Copying pictures and icons",
        "Writing HTML, CSS and JavaScript",
        "Saving the editable project",
    ]
    started = time.perf_counter()
    draw_progress(box, "Reconstructing the page", stages, 0)

    try:
        plan = ai.make_plan(summary)
        draw_progress(box, "Reconstructing the page", stages, 1)

        folder = app.output_folder_for(url)
        site = app.build_editable_site(analysis["data"], summary, plan, url, folder)
        draw_progress(box, "Reconstructing the page", stages, 3)

        app.save_data(url, analysis["data"])
        app.save_summary(url, summary)
        app.save_plan(url, plan)
    except Exception as error:
        box.empty()
        st.error("Something went wrong while building the page. " + str(error))
        return False

    box.empty()

    st.session_state["result"] = {
        "html": site["html"],
        "css": site["css"],
        "js": site["js"],
        "plan": plan,
        "images": site["assets"],
        "pieces": site.get("elements", 0),
        "folder": folder,
        "seconds": round(time.perf_counter() - started, 1),
        "loaded": False,
    }
    return True


# ---------------------------------------------------------------------------
# The rebuilt page, made self-contained for the preview frame
# ---------------------------------------------------------------------------
def preview_page(result):
    """Turn the saved files into one page for the preview box."""
    page = result["html"].replace(
        '<link rel="stylesheet" href="style.css">', "<style>" + result["css"] + "</style>"
    )
    page = page.replace(
        '<script src="script.js" defer></script>', "<script>" + result["js"] + "</script>"
    )

    folder = Path(result["folder"])

    def inline(match):
        relative = match.group(1)
        path = folder / relative

        try:
            data = path.read_bytes()
        except OSError:
            return match.group(0)

        if len(data) > MAX_PREVIEW_IMAGE_BYTES:
            # Too heavy to paste inline: the file is still in the project.
            return 'src=""'

        ending = path.suffix.lower().lstrip(".")
        mime = "image/svg+xml" if ending == "svg" else "image/" + ending.replace("jpg", "jpeg")
        encoded = base64.b64encode(data).decode("ascii")

        return 'src="data:' + mime + ";base64," + encoded + '"'

    return re.sub(r'src="(assets/images/[^"]+)"', inline, page)


# ---------------------------------------------------------------------------
# The Figma handoff dialog
# ---------------------------------------------------------------------------
@st.dialog("Export to Figma", width="medium")
def figma_dialog(title, url, folder, palette, structure):
    st.markdown(
        '<div class="notice ok" style="margin-bottom:14px">' + CHECK_SVG
        + "<span><b>Handoff bundle ready.</b> Code, assets and import notes, "
        "packaged in one zip.</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<ol class="steps-ol">'
        '<li><span class="sn">1</span><span>Download the bundle below.</span></li>'
        '<li><span class="sn">2</span><span>Unzip it and open <code>index.html</code> to '
        "check the page.</span></li>"
        '<li><span class="sn">3</span><span>Import that page with an HTML-to-Figma importer. '
        "Frames, text and images arrive as editable layers.</span></li>"
        '<li><span class="sn">4</span><span>Install the page fonts locally, or map them to '
        "your Figma library.</span></li>"
        "</ol>",
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

    st.download_button(
        "Download handoff bundle",
        data=bundle_bytes(folder, figma_readme(title, url)),
        file_name=app.domain_name(url).replace(".", "-") + "-figma-handoff.zip",
        mime="application/zip",
        type="primary",
        width="stretch",
        on_click="ignore",
        key="figma-download",
    )

    st.caption(
        "This app writes HTML, CSS, JavaScript and images rather than native .fig files. "
        "The bundle is structured so an HTML importer can rebuild it as editable layers."
    )

    with st.expander("Design tokens (copy into Figma variables)"):
        st.code(design_tokens(palette, structure), language="json")


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Frontend Reconstructor",
    page_icon="◧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("<style>" + CSS + "</style>", unsafe_allow_html=True)

analysis = st.session_state.get("analysis")
result = st.session_state.get("result")

# --- Sidebar ---------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">' + BRAND_SVG + "</div>"
        '<div class="brand-text"><span class="brand-name">Frontend Reconstructor</span>'
        '<span class="brand-sub">Local workspace</span></div></div>',
        unsafe_allow_html=True,
    )

    st.button(
        "New reconstruction",
        type="primary",
        width="stretch",
        icon=":material/add:",
        on_click=start_over,
    )

    projects = recent_projects()
    st.markdown(
        '<div class="side-label"><span>Projects</span><span class="count">'
        + str(len(projects))
        + "</span></div>",
        unsafe_allow_html=True,
    )

    if projects:
        for name in projects:
            st.button(
                name,
                key="project-" + name,
                width="stretch",
                on_click=open_project,
                args=(name,),
            )
    else:
        st.markdown(
            '<p class="side-empty">No runs yet. Pages you reconstruct are kept here.</p>',
            unsafe_allow_html=True,
        )

    if analysis:
        state_text = "Preview ready" if result else "Ready to rebuild"
        st.markdown(
            '<div class="side-rule"></div>'
            '<div class="side-current"><div class="side-label" style="padding:6px 0 8px">'
            '<span>Current run</span></div>'
            '<div class="host">' + escape(app.domain_name(analysis["url"])) + "</div>"
            '<div class="state"><span class="dot"></span>' + state_text + "</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="side-foot"><div class="side-rule"></div>'
        '<div class="side-foot-row"><span>Engine</span><b>Chromium</b></div>'
        '<div class="side-foot-row"><span>Storage</span><b>output/</b></div>'
        '<p>Runs on this machine. Only the page you enter is opened.</p></div>',
        unsafe_allow_html=True,
    )

# --- Header ----------------------------------------------------------------
if analysis:
    host = app.domain_name(analysis["url"])
    heading = analysis["summary"].get("main_heading") or analysis["summary"].get("title")
    heading = heading or host
    lede = '<p class="lede url">' + escape(analysis["url"]) + "</p>"
    crumb = (
        "Workspace <span class=\"sep\">/</span> <b>" + escape(host) + "</b>"
    )
else:
    heading = "Reconstruct any page into editable layers."
    lede = (
        '<p class="lede">Paste a public URL. The page is read in a real browser, then '
        "written back out as HTML, CSS and JavaScript you can edit — and hand to Figma "
        "as a starting point.</p>"
    )
    crumb = 'Workspace <span class="sep">/</span> <b>New reconstruction</b>'

if result:
    status = '<span class="chip ok"><span class="dot"></span>Preview ready</span>'
elif analysis:
    status = '<span class="chip live"><span class="dot"></span>Ready to rebuild</span>'
else:
    status = '<span class="chip quiet"><span class="dot"></span>Waiting for a URL</span>'

st.markdown(
    '<div class="ws-head"><div><div class="crumb">' + crumb + "</div><h1>"
    + escape(heading) + "</h1>" + lede + '</div><div class="ws-status">'
    + status + "</div></div>",
    unsafe_allow_html=True,
)

stepper(4 if result else (2 if analysis else 0))

# --- Command bar -----------------------------------------------------------
with st.container(key="panel-command"):
    st.markdown(
        '<div class="command-head"><div class="icon-tile">' + LINK_SVG + "</div>"
        '<div><div class="command-title">Page address</div>'
        '<div class="command-sub">One public page per run. Nothing is stored on a server.</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )

    input_col, button_col = st.columns([1, 0.24], gap="small", vertical_alignment="bottom")

    with input_col:
        st.text_input(
            "Website address",
            key="url_input",
            placeholder="https://example.com",
            label_visibility="collapsed",
        )

    with button_col:
        analyse_clicked = st.button(
            "Analyze page",
            type="primary",
            width="stretch",
            icon=":material/search:",
        )

    st.markdown(
        '<p class="hint">Sign-ins, paywalls and CAPTCHAs are never bypassed. '
        "Reconstruction usually takes 20–60 seconds.</p>",
        unsafe_allow_html=True,
    )

    analysis_box = st.empty()

if analyse_clicked:
    if run_analysis(analysis_box):
        st.rerun()
    else:
        analysis = st.session_state.get("analysis")
        result = st.session_state.get("result")

st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

# --- Workspace columns -----------------------------------------------------
left, right = st.columns([1.68, 1], gap="large")

# ============================ LEFT ========================================
with left:
    if not analysis:
        with st.container(key="panel-empty"):
            panel_head(
                "What a run produces",
                "A folder per site, with the whole page as editable files.",
            )

            st.markdown(
                '<div class="tree"><b>output/example.com/</b><br>'
                "├── <b>index.html</b> <span class=\"c\">structure, real elements</span><br>"
                "├── <b>style.css</b> <span class=\"c\">layout, type, colour</span><br>"
                "├── <b>script.js</b> <span class=\"c\">menus and toggles</span><br>"
                "├── assets/images/ <span class=\"c\">pictures and icons</span><br>"
                "└── reference/ <span class=\"c\">screenshot, for comparison</span></div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                '<ul class="checks">'
                "<li>" + CHECK_SVG + "<span><b>Rebuilt, not captured.</b> Text, headings, "
                "links and menus are ordinary HTML you can edit.</span></li>"
                "<li>" + CHECK_SVG + "<span><b>Responsive by default.</b> The page keeps its "
                "own breakpoints and the mobile navigation works.</span></li>"
                "<li>" + CHECK_SVG + "<span><b>Preview before you download.</b> Check desktop, "
                "tablet and phone widths inside the workspace.</span></li>"
                "</ul>",
                unsafe_allow_html=True,
            )

    if analysis:
        summary = analysis["summary"]
        palette = summary.get("palette") or {}
        counts = structure_of(analysis).get("counts") or {}
        seconds = analysis.get("seconds")
        time_chip = chip(str(seconds) + " s", "mono") if seconds else chip("Loaded", "quiet")

        with st.container(key="panel-analysis"):
            panel_head(
                "Analysis",
                "Read from the live page just now.",
                time_chip,
            )

            metric_strip(
                [
                    ("Elements", counts.get("elements", "—")),
                    ("Headings", len(summary.get("headings") or [])),
                    ("Text blocks", len(summary.get("paragraphs") or [])),
                    ("Links", counts.get("links", "—")),
                    ("Images", len(summary.get("images") or [])),
                ]
            )

            structure_tab, colour_tab, type_tab = st.tabs(["Structure", "Colours", "Type"])

            with structure_tab:
                headings = summary.get("headings") or []

                if headings:
                    rows = []

                    for item in headings[:12]:
                        level = int(item.get("level") or 2)
                        tag = "h" + str(level)
                        rows.append(
                            '<li class="lv' + str(level) + '" style="padding-left:'
                            + str((level - 1) * 14)
                            + 'px"><span class="tag">'
                            + tag
                            + '</span><span class="txt">'
                            + escape(str(item.get("text", "")))
                            + "</span></li>"
                        )

                    if len(headings) > 12:
                        rows.append(
                            '<li class="more">+' + str(len(headings) - 12)
                            + " more headings</li>"
                        )

                    st.markdown('<ul class="outline">' + "".join(rows) + "</ul>",
                                unsafe_allow_html=True)
                else:
                    st.markdown('<p class="hint">No headings were found on this page.</p>',
                                unsafe_allow_html=True)

                description = structure_of(analysis).get("description")
                if description:
                    st.markdown(
                        '<p class="hint" style="margin-top:10px">'
                        + escape(description)
                        + "</p>",
                        unsafe_allow_html=True,
                    )

            with colour_tab:
                seen = palette.get("seen") or {}
                items = []

                for value, roles in list(seen.items())[:10]:
                    label = ", ".join(str(role) for role in roles[:2])
                    items.append(
                        '<div class="sw-item"><span class="sw" style="background:'
                        + escape(value)
                        + '"></span><div style="min-width:0"><div class="sw-hex">'
                        + escape(value.upper())
                        + '</div><div class="sw-role">'
                        + escape(label)
                        + "</div></div></div>"
                    )

                if items:
                    st.markdown('<div class="swatch-grid">' + "".join(items) + "</div>",
                                unsafe_allow_html=True)
                else:
                    st.markdown('<p class="hint">No colours were read from this page.</p>',
                                unsafe_allow_html=True)

                st.markdown(
                    '<p class="hint" style="margin-top:10px">Background '
                    + escape(palette.get("background", "—"))
                    + " · Text " + escape(palette.get("text", "—"))
                    + " · Accent " + escape(palette.get("accent", "—")) + "</p>",
                    unsafe_allow_html=True,
                )

            with type_tab:
                body = structure_of(analysis).get("body") or {}
                family = body.get("fontFamily") or "Not captured"

                st.markdown(
                    '<div class="rows">'
                    '<div class="row"><span class="k">Body font</span><span class="v">'
                    + escape(str(family)) + "</span></div>"
                    '<div class="row"><span class="k">Base size</span><span class="v">'
                    + escape(str(body.get("size", "—"))) + " px</span></div>"
                    '<div class="row"><span class="k">Line height</span><span class="v">'
                    + escape(str(body.get("lineHeight", "—"))) + "</span></div>"
                    '<div class="row"><span class="k">Page width</span><span class="v">'
                    + escape(str(body.get("width", "—"))) + " px</span></div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

            if not result:
                st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

                if analysis.get("data"):
                    rebuild = st.button(
                        "Reconstruct page",
                        type="primary",
                        icon=":material/layers:",
                    )
                    st.markdown(
                        '<p class="hint">Writes index.html, style.css, script.js and the '
                        "image assets into <code>output/" + escape(app.domain_name(analysis["url"]))
                        + "</code>.</p>",
                        unsafe_allow_html=True,
                    )
                else:
                    rebuild = False
                    st.markdown(
                        '<p class="hint">This run was loaded from disk, so its captured '
                        "structure is not available. Analyse the address again to rebuild.</p>",
                        unsafe_allow_html=True,
                    )

                generation_box = st.empty()
            else:
                rebuild = False

        if not result and rebuild:
            if run_generation(generation_box, analysis):
                st.rerun()

    if result:
        images = result.get("images") or []
        result_seconds = result.get("seconds")
        build_chip = (
            chip("Built in " + str(result_seconds) + " s", "ok")
            if result_seconds
            else chip("Loaded from disk", "quiet")
        )

        with st.container(key="panel-preview"):
            panel_head(
                "Preview",
                "The rebuilt page, drawn from its own HTML and CSS.",
                build_chip,
            )

            metric_strip(
                [
                    ("Elements", result.get("pieces") or "—"),
                    ("Assets", len(images)),
                    ("Files", len(output_rows(result["folder"]))),
                    ("Mode", "Offline" if result["plan"].get("mode") == "offline" else "AI plan"),
                ]
            )

            device_col, view_col = st.columns(2, gap="small")

            with device_col:
                device = st.segmented_control(
                    "Preview width",
                    ["Desktop", "Tablet", "Mobile"],
                    default="Desktop",
                    key="device",
                    label_visibility="collapsed",
                    width="stretch",
                )

            with view_col:
                view = st.segmented_control(
                    "Preview view",
                    ["Rebuilt", "Reference"],
                    default="Rebuilt",
                    key="view",
                    label_visibility="collapsed",
                    width="stretch",
                )

            device = device or "Desktop"
            view = view or "Rebuilt"

            if view == "Reference":
                reference = reference_path(result["folder"], analysis["url"])

                if reference:
                    with st.container(key="reference-scroll"):
                        st.image(str(reference), width="stretch")
                    st.markdown(
                        '<p class="hint">Full-page screenshot of the original site, kept for '
                        "comparison only. It is never used as the page background.</p>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="notice note"><span>i</span><span>No reference screenshot '
                        "was saved for this page.</span></div>",
                        unsafe_allow_html=True,
                    )
            else:
                with st.container(key="frame-" + device.lower()):
                    st.iframe(
                        preview_page(result),
                        height=DEVICE_HEIGHTS[device],
                        width="stretch",
                    )

                st.markdown(
                    '<p class="hint">Scroll inside the frame to read the whole page. '
                    "Menus and the mobile navigation are live.</p>",
                    unsafe_allow_html=True,
                )

            if result["plan"].get("mode") == "offline":
                st.markdown(
                    '<div class="notice note"><span>i</span><span>'
                    "<b>No AI was used.</b> No API key was found, so the page was rebuilt "
                    "from its own structure and words.</span></div>",
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

            st.markdown(
                '<div class="files-label"><span>Files</span><span class="path">'
                + escape(str(result["folder"]))
                + "</span></div>",
                unsafe_allow_html=True,
            )

            dl_html, dl_css, dl_js, dl_zip = st.columns(4, gap="small")

            with dl_html:
                st.download_button(
                    "index.html",
                    data=result["html"],
                    file_name="index.html",
                    mime="text/html",
                    width="stretch",
                )

            with dl_css:
                st.download_button(
                    "style.css",
                    data=result["css"],
                    file_name="style.css",
                    mime="text/css",
                    width="stretch",
                )

            with dl_js:
                st.download_button(
                    "script.js",
                    data=result["js"],
                    file_name="script.js",
                    mime="text/javascript",
                    width="stretch",
                )

            with dl_zip:
                st.download_button(
                    "Bundle .zip",
                    data=bundle_bytes(result["folder"]),
                    file_name=app.domain_name(analysis["url"]).replace(".", "-") + "-rebuild.zip",
                    mime="application/zip",
                    width="stretch",
                )

            with st.expander("Section notes (" + result["plan"].get("mode", "offline") + ")"):
                st.markdown(
                    '<p class="hint"><b>'
                    + escape(result["plan"].get("title", ""))
                    + "</b> · "
                    + escape(result["plan"].get("tagline", ""))
                    + "</p>",
                    unsafe_allow_html=True,
                )

                note_rows = []

                for section in result["plan"].get("sections", []):
                    note_rows.append(
                        '<div class="row" style="display:block">'
                        '<div style="font-size:12.5px;font-weight:500">'
                        + escape(section.get("heading", ""))
                        + '</div><div class="hint" style="margin-top:3px">'
                        + escape(section.get("body", ""))
                        + "</div></div>"
                    )

                st.markdown('<div class="rows">' + "".join(note_rows) + "</div>",
                            unsafe_allow_html=True)

# ============================ RIGHT =======================================
with right:
    if not analysis:
        with st.container(key="panel-rules"):
            panel_head("Before you start", "A few limits that keep this tool usable.")

            st.markdown(
                '<ul class="checks">'
                "<li>" + CHECK_SVG + "<span><b>Public pages only.</b> Nothing behind a "
                "sign-in, a paywall or a CAPTCHA is opened.</span></li>"
                "<li>" + CHECK_SVG + "<span><b>One page at a time.</b> The address you "
                "enter is the only page loaded.</span></li>"
                "<li>" + CHECK_SVG + "<span><b>Images belong to their site.</b> They are "
                "copied for personal, reference use.</span></li>"
                "</ul>",
                unsafe_allow_html=True,
            )

        with st.container(key="panel-stack"):
            panel_head("Under the hood", "Everything stays on this machine.")

            st.markdown(
                '<div class="rows">'
                '<div class="row"><span class="k">Browser</span><span class="v">Chromium 1440px</span></div>'
                '<div class="row"><span class="k">Capture</span><span class="v">live DOM + styles</span></div>'
                '<div class="row"><span class="k">Output</span><span class="v">HTML · CSS · JS</span></div>'
                '<div class="row"><span class="k">Network</span><span class="v">page + assets only</span></div>'
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="hint">Nothing is uploaded. Screenshots are reference only and '
                "never used as the page background.</p>",
                unsafe_allow_html=True,
            )

    if analysis:
        palette = analysis["summary"].get("palette") or {}
        structure = structure_of(analysis)

        if result:
            with st.container(key="panel-figma"):
                panel_head(
                    "Export to Figma",
                    "Hand the rebuilt page to Figma as editable layers.",
                    chip("Ready", "ok"),
                )

                st.markdown(
                    '<div class="rows">'
                    '<div class="row"><span class="k">HTML structure</span><span class="v">'
                    + ("ready" if result["html"] else "missing")
                    + "</span></div>"
                    '<div class="row"><span class="k">Stylesheet</span><span class="v">'
                    + ("ready" if result["css"] else "missing")
                    + "</span></div>"
                    '<div class="row"><span class="k">Image assets</span><span class="v">'
                    + str(len(result.get("images") or [])) + " files</span></div>"
                    '<div class="row"><span class="k">Import notes</span><span class="v">'
                    "FIGMA.md</span></div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

                export_clicked = st.button(
                    "Export for Figma",
                    type="primary",
                    width="stretch",
                    icon=":material/ios_share:",
                )

                st.markdown(
                    '<p class="hint">Downloads one zip with the code, assets and a short '
                    "import guide.</p>",
                    unsafe_allow_html=True,
                )

                if export_clicked:
                    figma_dialog(
                        analysis["summary"].get("title") or app.domain_name(analysis["url"]),
                        analysis["url"],
                        result["folder"],
                        palette,
                        structure,
                    )
        else:
            with st.container(key="panel-figma"):
                panel_head(
                    "Export to Figma",
                    "Unlocks after the page is reconstructed.",
                    chip("Locked", "quiet"),
                )

                st.markdown(
                    '<ol class="steps-ol locked">'
                    '<li><span class="sn">1</span><span>Analyse a page</span></li>'
                    '<li><span class="sn">2</span><span>Reconstruct it into HTML, CSS and JS</span></li>'
                    '<li><span class="sn">3</span><span>Export the handoff bundle</span></li>'
                    "</ol>",
                    unsafe_allow_html=True,
                )

                st.markdown(
                    '<p class="hint">The export carries real layers, not a flattened image.</p>',
                    unsafe_allow_html=True,
                )

        with st.container(key="panel-run"):
            panel_head("Run details", "Where this page came from.")

            rows = [
                ("Source", app.domain_name(analysis["url"])),
                ("Mode", "Offline rebuild" if (result or {}).get("plan", {}).get("mode") == "offline" else "AI plan"),
                ("Analysed", (str(analysis["seconds"]) + " s") if analysis.get("seconds") else "Loaded"),
            ]

            if result:
                rows.append(("Built", (str(result["seconds"]) + " s") if result.get("seconds") else "Loaded"))
                rows.append(("Saved", str(result["folder"])))

            row_html = "".join(
                '<div class="row"><span class="k">' + label
                + '</span><span class="v">' + escape(str(value)) + "</span></div>"
                for label, value in rows
            )
            st.markdown('<div class="rows">' + row_html + "</div>", unsafe_allow_html=True)

        if result:
            with st.container(key="panel-output"):
                panel_head("Output files", "Saved on disk and downloadable above.")

                files = output_rows(result["folder"])
                file_html = "".join(
                    '<div class="row"><span class="k" style="font-family:var(--mono);'
                    "font-size:11px;color:var(--ink)\">" + escape(name)
                    + '</span><span class="v">' + escape(size) + "</span></div>"
                    for name, size in files
                )
                st.markdown('<div class="rows">' + file_html + "</div>", unsafe_allow_html=True)

st.markdown(
    '<p class="hint" style="margin-top:26px">The rebuilt files live in your '
    "<code>output</code> folder as well as in the download buttons. Best used on pages "
    "you are allowed to inspect.</p>",
    unsafe_allow_html=True,
)
