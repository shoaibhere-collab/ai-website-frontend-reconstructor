# reconstruct.py
# Rebuild the page you asked for as editable HTML, CSS and JavaScript.
#
# The earlier steps could only describe a page (its headings, a few paragraphs
# and some colours), so build.py had to invent a new page from that
# description. This file does the opposite: it reads the real structure of the
# live page - sections, navigation, headings, cards, lists, buttons, pictures -
# and writes that same structure out as ordinary HTML elements, with a
# stylesheet that copies the layout it found.
#
# Nothing here looks at a screenshot. Pictures are saved one by one into
# assets/images/ and placed where they belong in the page.

import re
import shutil
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import assets

# How much of a page we copy. Big pages stop at these limits instead of
# producing a file nobody can open.
MAX_NODES = 1400
MAX_DEPTH = 14
MAX_TEXT_CHARS = 600
MAX_ASSETS = 30

INDENT = "  "
VOID_TAGS = {"img", "br", "hr", "input"}


# ---------------------------------------------------------------------------
# Step 1: read the page in the browser
# ---------------------------------------------------------------------------
# This runs inside the real page. It walks the visible elements and records
# the layout that matters (flex or grid, gaps, padding, colours, type sizes),
# plus the text, links, pictures and buttons. No screenshot is involved.
EXTRACT_JS = r"""
() => {
  const MAX_NODES = 1400;
  const MAX_DEPTH = 14;

  const SKIP_TAGS = new Set([
    "SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "LINK", "META", "HEAD",
    "BASE", "TITLE", "IFRAME", "CANVAS", "VIDEO", "AUDIO", "OBJECT", "EMBED"
  ]);

  const ROLES = {
    h1: "heading", h2: "heading", h3: "heading", h4: "subheading",
    h5: "subheading", h6: "subheading",
    p: "text", a: "link", button: "button", img: "image",
    ul: "list", ol: "list", li: "item",
    nav: "nav", header: "header", footer: "footer", main: "main",
    section: "section", article: "article", aside: "aside",
    div: "block", span: "span", figure: "figure", figcaption: "caption",
    form: "form", label: "label", input: "field", textarea: "field",
    select: "field", table: "table", tr: "row", td: "cell", th: "cell",
    blockquote: "quote", hr: "rule", strong: "strong", em: "emphasis",
    b: "strong", i: "emphasis", small: "small", time: "time",
    address: "address", svg: "icon"
  };

  let nodeCount = 0;

  // Every element that some button says it opens with aria-controls. Those
  // elements are usually hidden until the button is pressed, so they are
  // captured on purpose: they are the site's menus.
  const CONTROLLED = (() => {
    const ids = new Set();
    document.querySelectorAll("[aria-controls]").forEach(element => {
      (element.getAttribute("aria-controls") || "").split(/\s+/).forEach(id => {
        if (id) ids.add(id);
      });
    });
    return ids;
  })();

  function hasMenuTrigger(element) {
    const previous = element.previousElementSibling;

    if (previous) {
      const trigger = previous.matches("button, a")
        ? previous
        : previous.querySelector("button[aria-expanded], button[aria-haspopup], a[aria-haspopup]");
      if (trigger) return true;
    }

    const parent = element.parentElement;
    if (parent) {
      const trigger = parent.querySelector("button[aria-expanded], button[aria-haspopup]");
      if (trigger && !element.contains(trigger)) return true;
    }

    return false;
  }

  function hiddenMenu(element, style) {
    if (style.display !== "none" && style.visibility !== "hidden") return false;
    if (element.id && CONTROLLED.has(element.id)) return true;
    if (element.tagName !== "UL" && element.tagName !== "DIV") return false;
    if (element.querySelectorAll("a").length < 2) return false;
    return hasMenuTrigger(element);
  }

  function px(value) {
    const number = parseFloat(value);
    return isNaN(number) ? 0 : Math.round(number);
  }

  function isVisible(element, style) {
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (parseFloat(style.opacity || "1") < 0.05) return false;
    // Elements pinned to the window (cookie bars, chat bubbles) would cover
    // the page once rebuilt, so they are left out.
    if (style.position === "fixed") return false;
    const box = element.getBoundingClientRect();
    return box.width >= 1 && box.height >= 1;
  }

  function styleOf(style) {
    const out = {};
    const display = style.display;

    if (display.includes("flex")) out.display = "flex";
    else if (display.includes("grid")) out.display = "grid";
    else if (display === "inline" || display === "inline-block") out.display = "inline";

    if (out.display === "flex") {
      if (style.flexDirection !== "row") out.dir = style.flexDirection;
      if (style.flexWrap === "wrap" || style.flexWrap === "wrap-reverse") out.wrap = "wrap";
      const justify = style.justifyContent;
      if (justify && justify !== "normal" && justify !== "flex-start") out.justify = justify;
      const align = style.alignItems;
      if (align && align !== "normal" && align !== "stretch") out.align = align;
    }

    if (out.display === "flex" || out.display === "grid") {
      const columnGap = px(style.columnGap);
      const rowGap = px(style.rowGap);
      if (columnGap) out.gapX = columnGap;
      if (rowGap && rowGap !== columnGap) out.gapY = rowGap;
    }

    if (out.display === "grid") {
      const columns = style.gridTemplateColumns;
      const count = columns && columns !== "none"
        ? columns.split(" ").filter(Boolean).length
        : 1;
      out.cols = count;
    }

    const padding = [
      px(style.paddingTop), px(style.paddingRight),
      px(style.paddingBottom), px(style.paddingLeft)
    ];
    if (padding.some(value => value)) out.pad = padding;

    // Negative margins were used to break an element out of its column; copying
    // them makes a rebuilt page overlap itself, so they become 0.
    const margin = [
      Math.max(0, px(style.marginTop)), Math.max(0, px(style.marginRight)),
      Math.max(0, px(style.marginBottom)), Math.max(0, px(style.marginLeft))
    ];
    if (margin.some(value => value)) out.mar = margin;

    if (style.backgroundColor && style.backgroundColor !== "rgba(0, 0, 0, 0)") {
      out.bg = style.backgroundColor;
    }

    out.color = style.color;
    out.size = px(style.fontSize) || 16;
    out.weight = style.fontWeight;
    if (style.fontStyle === "italic") out.italic = 1;

    const lineHeight = parseFloat(style.lineHeight);
    if (!isNaN(lineHeight) && out.size) {
      out.lh = Math.round((lineHeight / out.size) * 100) / 100;
    }

    const spacing = parseFloat(style.letterSpacing);
    if (!isNaN(spacing) && Math.abs(spacing) >= 0.1) {
      out.ls = Math.round(spacing * 100) / 100;
    }

    if (style.textAlign && style.textAlign !== "start" && style.textAlign !== "left") {
      out.textAlign = style.textAlign;
    }
    if (style.textTransform && style.textTransform !== "none") {
      out.transform = style.textTransform;
    }
    if ((style.textDecorationLine || "").includes("underline")) out.underline = 1;

    const borderWidth = Math.max(
      px(style.borderTopWidth), px(style.borderRightWidth),
      px(style.borderBottomWidth), px(style.borderLeftWidth)
    );
    if (borderWidth > 0 && style.borderTopStyle !== "none") {
      out.border = borderWidth;
      out.borderStyle = style.borderTopStyle;
      out.borderColor = style.borderTopColor;
    }

    const radius = Math.max(
      px(style.borderTopLeftRadius), px(style.borderTopRightRadius),
      px(style.borderBottomLeftRadius), px(style.borderBottomRightRadius)
    );
    if (radius) out.radius = radius;

    if (style.maxWidth && style.maxWidth !== "none") {
      const maxWidth = px(style.maxWidth);
      if (maxWidth) out.maxw = maxWidth;
    }

    if (style.listStyleType && ["disc", "decimal", "none"].indexOf(style.listStyleType) === -1) {
      out.listStyle = style.listStyleType;
    }
    if (style.listStyleType === "none") out.listNone = 1;

    return out;
  }

  function build(element, depth, force) {
    if (nodeCount >= MAX_NODES || depth > MAX_DEPTH) return null;
    if (SKIP_TAGS.has(element.tagName)) return null;

    const style = getComputedStyle(element);
    const tag = element.tagName.toLowerCase();

    if (style.display === "contents") {
      // The element adds no box of its own: keep what is inside it instead.
      const inner = [];
      for (const child of element.children) {
        const built = build(child, depth, force);
        if (built && !built.contents) inner.push(built);
        if (nodeCount >= MAX_NODES) break;
      }
      return { tag: "span", role: "span", contents: true, style: {}, kids: inner };
    }

    const visible = isVisible(element, style);
    const menuPanel = !visible && !force && hiddenMenu(element, style);

    if (!visible && !force && !menuPanel) return null;

    const box = element.getBoundingClientRect();

    // Anything this small is usually text meant only for screen readers, or a
    // tracking pixel. Real rules (hr) are allowed through.
    if (visible && tag !== "hr" && box.width < 8 && box.height < 8) return null;

    // An icon drawn inline: keep its markup, it stays sharp and editable.
    if (tag === "svg") {
      if (!visible) return null;
      const markup = element.outerHTML;
      if (markup.length > 20000) return null;
      nodeCount += 1;
      return {
        tag: "svg",
        role: "icon",
        markup: markup,
        w: Math.round(box.width),
        h: Math.round(box.height)
      };
    }

    if (tag === "br") return { tag: "br", role: "break" };
    if (tag === "input" && element.type === "hidden") return null;

    nodeCount += 1;

    const node = {
      tag: tag,
      role: ROLES[tag] || "block",
      w: Math.round(box.width),
      h: Math.round(box.height),
      style: menuPanel ? {} : styleOf(style),
      kids: []
    };

    // A captured menu panel: hidden in the page, opened by its button.
    if (menuPanel) {
      node.panel = true;
      if (element.id) node.id = element.id;
    }

    // A button that says it opens something is the trigger for that menu.
    if ((tag === "button" || tag === "a") && !menuPanel) {
      if (element.hasAttribute("aria-expanded") || element.hasAttribute("aria-haspopup")) {
        node.expandable = true;

        const controls = (element.getAttribute("aria-controls") || "").trim();
        if (controls) node.controls = controls.split(/\s+/)[0];
      }
    }

    if (tag === "img") {
      node.src = element.currentSrc || element.src || "";
      node.alt = element.getAttribute("alt") || "";
      node.nw = element.naturalWidth || Math.round(box.width);
      node.nh = element.naturalHeight || Math.round(box.height);
      if (!node.src) return null;
      return node;
    }

    if (tag === "a") {
      const href = element.href || "";
      if (href && !href.startsWith("javascript:")) node.href = href;
      if (element.getAttribute("target")) node.target = element.getAttribute("target");
    }

    if (tag === "input" || tag === "select" || tag === "textarea") {
      node.type = element.getAttribute("type") || (tag === "textarea" ? "textarea" : "text");
      node.placeholder = element.getAttribute("placeholder") || "";
      node.label = element.getAttribute("aria-label") || "";
      node.value = (element.value || "").slice(0, 120);
      if (tag === "select") {
        const chosen = element.options[element.selectedIndex];
        node.text = chosen ? chosen.text.slice(0, 80) : "";
      }
      return node;
    }

    // Text and elements are kept in the order they appear, so a sentence with
    // links inside it reads exactly as it did on the original page.
    const kids = [];
    let letters = 0;

    for (const child of element.childNodes) {
      if (child.nodeType === 3) {
        const text = child.nodeValue.replace(/\s+/g, " ");
        if (text.trim() && letters < 900) {
          kids.push({ text: text });
          letters += text.length;
        }
        continue;
      }

      if (child.nodeType !== 1) continue;

      const built = build(child, depth + 1, force || menuPanel);
      if (built) {
        if (built.contents) {
          for (const inner of built.kids) kids.push(inner);
        } else {
          kids.push(built);
        }
      }
      if (nodeCount >= MAX_NODES) break;
    }

    const paints = node.style.bg || node.style.border || node.style.pad || node.style.radius;
    const wrappers = ["div", "span", "section", "article"];

    // A plain wrapper that holds exactly one element adds nothing but noise.
    if (
      !menuPanel && kids.length === 1 && kids[0].tag && !paints && !node.style.display &&
      wrappers.indexOf(tag) !== -1
    ) {
      return kids[0];
    }

    node.kids = kids;

    // Nothing to show and nothing painted: leave it out.
    if (!kids.length && !paints && !node.text && tag !== "hr") return null;

    return node;
  }

  function bodyStyle() {
    const style = getComputedStyle(document.body);
    const rootStyle = getComputedStyle(document.documentElement);
    const box = document.body.getBoundingClientRect();
    const padding = [
      px(style.paddingTop), px(style.paddingRight),
      px(style.paddingBottom), px(style.paddingLeft)
    ];

    let maxWidth = 0;
    if (style.maxWidth && style.maxWidth !== "none") maxWidth = px(style.maxWidth);

    // Many pages keep their writing in a centred column narrower than the window.
    const centered = box.width > 0 && box.width < window.innerWidth - 8 && box.left > 8;

    let background = style.backgroundColor;
    if (!background || background === "rgba(0, 0, 0, 0)") background = rootStyle.backgroundColor;
    if (!background || background === "rgba(0, 0, 0, 0)") background = "rgb(255, 255, 255)";

    return {
      background: background,
      color: style.color,
      fontFamily: style.fontFamily,
      size: px(style.fontSize) || 17,
      lineHeight: (parseFloat(style.lineHeight) || 27) / (px(style.fontSize) || 17),
      padding: padding.some(value => value) ? padding : null,
      maxWidth: maxWidth,
      centered: centered,
      width: Math.round(box.width)
    };
  }

  const nodes = [];
  for (const child of document.body.children) {
    const built = build(child, 0);
    if (built && !built.contents) nodes.push(built);
    if (nodeCount >= MAX_NODES) break;
  }

  const description = document.querySelector('meta[name="description"]');

  return {
    url: location.href,
    title: (document.title || "").replace(/\s+/g, " ").trim(),
    description: description ? (description.getAttribute("content") || "").slice(0, 300) : "",
    lang: document.documentElement.lang || "en",
    body: bodyStyle(),
    nodes: nodes,
    counts: {
      elements: nodeCount,
      images: document.images.length,
      links: document.links.length
    }
  };
}
"""


def extract(page):
    """Read the structure of the open page. Returns a dict (possibly empty)."""
    try:
        data = page.evaluate(EXTRACT_JS)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def count_nodes(node):
    """How many elements this branch holds."""
    if not isinstance(node, dict):
        return 0
    return 1 + sum(count_nodes(child) for child in node.get("kids", []))


# ---------------------------------------------------------------------------
# Step 2: save the pictures as individual files
# ---------------------------------------------------------------------------
def safe_name(src, used):
    """Turn a picture address into a short file name that is not taken yet."""
    stem = Path(urlparse(src).path).stem or "image"
    stem = re.sub(r"[^a-zA-Z0-9._-]", "-", stem).strip("-.").lower()
    stem = stem[:40] or "image"

    name = stem
    number = 2
    while name in used:
        name = stem + "-" + str(number)
        number += 1

    used.add(name)
    return name


def download_assets(tree, folder, limit=MAX_ASSETS):
    """Save every picture into folder. Returns {original address: relative path}."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    mapping = {}
    used = set()
    saved = 0

    def visit(node):
        nonlocal saved

        if not isinstance(node, dict):
            return

        src = node.get("src", "")
        if node.get("tag") == "img" and src.startswith(("http://", "https://")):
            if saved < limit and src not in mapping:
                target = folder / safe_name(src, used)
                try:
                    ending = assets.download_one(src, target)
                except Exception:
                    ending = None        # one broken picture must not stop the rest

                if ending:
                    name = target.with_suffix(ending).name
                    mapping[src] = "assets/images/" + name
                    saved += 1

        for child in node.get("kids", []):
            visit(child)

    for node in tree.get("nodes", []):
        visit(node)

    return mapping


# ---------------------------------------------------------------------------
# Step 3: write the HTML
# ---------------------------------------------------------------------------
def css_color(value):
    """Turn 'rgb(43, 91, 132)' into '#2B5B84' so the CSS is easy to read."""
    text = str(value or "").strip()

    if not text.startswith("rgb"):
        return text

    numbers = re.findall(r"[\d.]+", text)
    if len(numbers) < 3:
        return text

    if text.startswith("rgba") and len(numbers) >= 4 and float(numbers[3]) == 0:
        return "transparent"

    parts = []
    for number in numbers[:3]:
        parts.append(max(0, min(255, int(float(number)))))

    return "#{:02X}{:02X}{:02X}".format(*parts)


def count_links(node):
    """How many links this branch holds."""
    total = 1 if node.get("tag") == "a" else 0
    return total + sum(count_links(child) for child in node.get("kids", []))


def prepare_interactions(tree):
    """Name the navigation toggles and pair every menu button with its panel.

    Without this, a menu would ship as a hidden list nobody can open, and the
    navigation would simply wrap on a phone instead of folding into a button.
    """
    index = {}

    def collect(node):
        if not node.get("tag"):
            return
        if node.get("id"):
            index.setdefault(node["id"], node)
        for child in node.get("kids", []):
            collect(child)

    for node in tree.get("nodes", []):
        collect(node)

    counts = {"menu": 0, "nav": 0}

    def walk(node, parent):
        if not node.get("tag"):
            return

        if node.get("expandable"):
            target = index.get(node.get("controls", ""))

            # No aria-controls: the panel is normally the block right after.
            if target is None and parent:
                siblings = parent.get("kids", [])
                try:
                    position = siblings.index(node)
                except ValueError:
                    position = -1

                for sibling in siblings[position + 1 :]:
                    if sibling.get("tag") and sibling.get("role") in ("list", "block", "nav"):
                        if not sibling.get("panel"):
                            target = sibling
                        break

            if target is not None and target is not node:
                counts["menu"] += 1
                name = "menu-" + str(counts["menu"])
                node["menu"] = name
                target["panel"] = True
                target["menu"] = name

        if node.get("tag") == "nav" and count_links(node) >= 2:
            counts["nav"] += 1
            node["nav_toggle"] = "nav-links-" + str(counts["nav"])

        for child in node.get("kids", []):
            walk(child, node)

    for node in tree.get("nodes", []):
        walk(node, None)

    def prune(node):
        """Drop a captured panel that ended up with no button to open it."""
        kids = []

        for child in node.get("kids", []):
            if child.get("panel") and not child.get("menu"):
                continue
            prune(child)
            kids.append(child)

        if "kids" in node:
            node["kids"] = kids

    for node in tree.get("nodes", []):
        prune(node)


def tree_flags(tree):
    """Whether the page needs the navigation and menu styles at all."""
    nav = menu = False

    def walk(node):
        nonlocal nav, menu
        if node.get("nav_toggle"):
            nav = True
        if node.get("panel"):
            menu = True
        for child in node.get("kids", []):
            walk(child)

    for node in tree.get("nodes", []):
        walk(node)

    return nav, menu


def assign_classes(tree):
    """Give every element one short, unique class name, in page order."""
    used = set()

    def walk(node):
        if not node.get("tag"):
            return                      # a run of text needs no class

        role = node.get("role") or "block"
        name = role
        number = 2
        while name in used:
            name = role + "-" + str(number)
            number += 1

        used.add(name)
        node["class"] = name + (" menu-panel" if node.get("panel") else "")

        for child in node.get("kids", []):
            walk(child)

    for node in tree.get("nodes", []):
        walk(node)


def html_attribute(value):
    return escape(str(value), quote=True)


# Elements that share a line with the words around them.
INLINE_TAGS = {"span", "strong", "em", "b", "i", "small", "time", "a", "button", "br", "img", "label", "svg"}


def opening_tag(node):
    """The start tag, with the attributes that make it work."""
    tag = node.get("tag", "div")
    attrs = ' class="' + node.get("class", "") + '"'

    if tag == "a":
        href = node.get("href", "")
        if href:
            attrs += ' href="' + html_attribute(href) + '"'
        if node.get("target") == "_blank":
            attrs += ' target="_blank" rel="noopener"'

    if tag == "button":
        attrs += ' type="button"'

    # A menu button and the panel it opens point at each other.
    if node.get("menu") and not node.get("panel"):
        attrs += (
            ' data-menu="'
            + node["menu"]
            + '" aria-controls="'
            + node["menu"]
            + '" aria-expanded="false" aria-haspopup="true"'
        )

    if node.get("panel"):
        attrs += ' id="' + node.get("menu", "") + '" hidden'

    if node.get("nav_toggle"):
        attrs += ' data-nav-toggle="false"'

    return "<" + tag + attrs + ">"


def render_field(node):
    """A form control, which is written as an empty tag."""
    tag = node.get("tag")
    cls = node.get("class", "")

    if tag == "textarea":
        return (
            '<textarea class="'
            + cls
            + '" rows="3" placeholder="'
            + html_attribute(node.get("placeholder", ""))
            + '">'
            + escape(node.get("text", ""))
            + "</textarea>"
        )

    if tag == "select":
        return (
            '<select class="'
            + cls
            + '"><option>'
            + escape(node.get("text", ""))
            + "</option></select>"
        )

    field = '<input class="' + cls + '"'

    if node.get("type"):
        field += ' type="' + html_attribute(node["type"]) + '"'
    if node.get("placeholder"):
        field += ' placeholder="' + html_attribute(node["placeholder"]) + '"'
    if node.get("label"):
        field += ' aria-label="' + html_attribute(node["label"]) + '"'

    return field + ">"


def is_inline(node):
    """True when this node belongs on the same line as the words beside it."""
    if not isinstance(node, dict):
        return False

    if not node.get("tag"):
        return True                     # a run of text

    if node.get("tag") in INLINE_TAGS:
        return True

    return (node.get("style") or {}).get("display") == "inline"


def render_fragment(node, saved_assets):
    """One line of HTML for an inline element, or for a run of text."""
    tag = node.get("tag")

    if not tag:
        return escape(node.get("text", ""))

    if tag == "br":
        return "<br>"

    if tag == "svg":
        return node.get("markup", "")

    if tag == "img":
        src = node.get("src", "")
        return (
            '<img class="'
            + node.get("class", "")
            + '" src="'
            + html_attribute(saved_assets.get(src, src))
            + '" alt="'
            + html_attribute(node.get("alt", ""))
            + '" loading="lazy">'
        )

    if tag in ("input", "select", "textarea"):
        return render_field(node)

    open_tag = opening_tag(node)

    if tag in VOID_TAGS:
        return open_tag

    inner = "".join(render_fragment(child, saved_assets) for child in node.get("kids", []))
    return open_tag + inner + "</" + tag + ">"


def render_node(node, depth, saved_assets):
    """Return the lines of HTML for this element and everything inside it."""
    if not isinstance(node, dict):
        return []

    tag = node.get("tag")
    pad = INDENT * (depth + 1)

    if not tag:
        return [pad + escape(node.get("text", ""))]

    if tag in ("br", "svg", "img", "input", "select", "textarea") or tag in VOID_TAGS:
        fragment = render_fragment(node, saved_assets)
        return [pad + fragment] if fragment else []

    open_tag = opening_tag(node)
    kids = node.get("kids", [])

    # A navigation carries a Menu button and one wrapper, so it can fold away
    # on a narrow screen without touching the links themselves.
    if tag == "nav" and node.get("nav_toggle") and kids:
        name = node["nav_toggle"]
        lines = [
            pad + open_tag,
            pad
            + INDENT
            + '<button class="nav-toggle" type="button" data-nav-button'
            ' aria-expanded="false" aria-controls="'
            + name
            + '">Menu</button>',
            pad + INDENT + '<div class="nav-links" id="' + name + '">',
        ]

        for child in kids:
            lines += render_node(child, depth + 2, saved_assets)

        lines.append(pad + INDENT + "</div>")
        lines.append(pad + "</" + tag + ">")
        return lines

    if not kids:
        return [pad + open_tag + "</" + tag + ">"]

    # A sentence with links inside it stays on one line, in its original order.
    if all(is_inline(child) for child in kids):
        inner = "".join(render_fragment(child, saved_assets) for child in kids)
        return [pad + open_tag + inner + "</" + tag + ">"]

    lines = [pad + open_tag]
    run = []

    for child in kids:
        if is_inline(child):
            run.append(render_fragment(child, saved_assets))
            continue

        if run:
            lines.append(INDENT * (depth + 2) + "".join(run).strip())
            run = []

        lines += render_node(child, depth + 1, saved_assets)

    if run:
        lines.append(INDENT * (depth + 2) + "".join(run).strip())

    lines.append(pad + "</" + tag + ">")
    return lines


def build_html(tree, data, source_url, saved_assets):
    """Return the whole page as editable HTML."""
    prepare_interactions(tree)
    assign_classes(tree)

    title = data.get("title") or "Rebuilt page"
    lang = (data.get("lang") or "en").split("-")[0] or "en"

    lines = [
        "<!DOCTYPE html>",
        '<html lang="' + html_attribute(lang) + '">',
        "<head>",
        INDENT + '<meta charset="utf-8">',
        INDENT + '<meta name="viewport" content="width=device-width, initial-scale=1">',
        INDENT + "<title>" + escape(title) + "</title>",
    ]

    if data.get("description"):
        lines.append(
            INDENT
            + '<meta name="description" content="'
            + html_attribute(data["description"])
            + '">'
        )

    lines += [
        INDENT + "<!-- Rebuilt from " + escape(source_url) + " -->",
        INDENT + "<!-- Structure, text, layout and colours are ordinary HTML and CSS. -->",
        INDENT + '<link rel="stylesheet" href="style.css">',
        "</head>",
        "<body>",
    ]

    for node in tree.get("nodes", []):
        lines += render_node(node, 0, saved_assets)

    lines += [
        INDENT + '<script src="script.js" defer></script>',
        "</body>",
        "</html>",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 4: write the CSS
# ---------------------------------------------------------------------------
def px(value):
    return str(int(round(value))) + "px"


def padding_value(values):
    """Write four sides the short way, so the CSS reads like hand-written CSS."""
    top, right, bottom, left = values

    if top == bottom and left == right and top == left:
        return px(top)
    if top == bottom and left == right:
        return px(top) + " " + px(left)

    return " ".join(px(value) for value in (top, right, bottom, left))


def usable(value, fallback):
    """Make sure a colour is something CSS understands."""
    text = css_color(value)
    if not text or text == "transparent":
        return fallback
    if text.startswith("#") or text.startswith("rgb") or text.startswith("hsl"):
        return text
    if re.fullmatch(r"[a-zA-Z]+", text):
        return text
    return fallback


def declarations(node, parent):
    """The CSS for one element, compared with the block it sits in."""
    style = node.get("style") or {}
    parent_style = (parent or {}).get("style") or {}
    tag = node.get("tag", "div")
    out = []

    display = style.get("display")

    if tag == "img":
        out.append("display: block")
        out.append("width: 100%")
        out.append("height: auto")
        if node.get("nw") and node.get("nh"):
            out.append(
                "aspect-ratio: " + str(node["nw"]) + " / " + str(node["nh"])
            )
        if style.get("radius"):
            out.append("border-radius: " + px(style["radius"]))
        if style.get("maxw"):
            out.append("max-width: " + px(style["maxw"]))
        return out

    if display == "flex":
        out.append("display: flex")
        out.append("flex-direction: " + style.get("dir", "row"))
        # Wrapping keeps a wide row readable on a phone.
        out.append("flex-wrap: " + ("wrap" if style.get("dir", "row") == "row" else "nowrap"))
        if style.get("justify"):
            out.append("justify-content: " + style["justify"])
        if style.get("align"):
            out.append("align-items: " + style["align"])
    elif display == "grid":
        columns = style.get("cols", 1)
        out.append("display: grid")
        if columns and columns > 1:
            width = node.get("w") or 0
            track = int(width / columns) if width else 220
            track = max(160, min(track, 380))
            out.append(
                "grid-template-columns: repeat(auto-fit, minmax(min("
                + str(track)
                + "px, 100%), 1fr))"
            )
        else:
            out.append("grid-template-columns: 1fr")
    elif display == "inline":
        out.append("display: inline-block")

    gap_x = style.get("gapX")
    gap_y = style.get("gapY") or gap_x

    if display in ("flex", "grid"):
        if gap_x and gap_y and gap_x == gap_y:
            out.append("gap: " + px(gap_x))
        else:
            if gap_y:
                out.append("row-gap: " + px(gap_y))
            if gap_x:
                out.append("column-gap: " + px(gap_x))

    padding = style.get("pad")
    if padding:
        out.append("padding: " + padding_value(padding))

    margin = style.get("mar")
    if margin:
        top, right, bottom, left = margin
        if top or bottom:
            out.append("margin-top: " + px(top))
            out.append("margin-bottom: " + px(bottom))
        if left and not parent_style.get("pad"):
            out.append("margin-left: " + px(left))
        if right and not parent_style.get("pad"):
            out.append("margin-right: " + px(right))

    if style.get("maxw"):
        out.append("width: 100%")
        out.append("max-width: " + px(style["maxw"]))
        out.append("margin-left: auto")
        out.append("margin-right: auto")

    if style.get("bg"):
        out.append("background-color: " + css_color(style["bg"]))

    if style.get("border"):
        out.append(
            "border: "
            + px(style["border"])
            + " "
            + (style.get("borderStyle") or "solid")
            + " "
            + css_color(style.get("borderColor") or "currentColor")
        )

    if style.get("radius"):
        out.append("border-radius: " + px(style["radius"]))

    # Typography and colour are only written when they differ from the block
    # around them, so the stylesheet stays short and readable.
    if style.get("size") and style["size"] != parent_style.get("size"):
        size = style["size"]
        if size >= 26:
            out.append(
                "font-size: clamp("
                + str(round(size * 0.66))
                + "px, "
                + str(round(size / 16 * 2.2, 1))
                + "vw, "
                + str(size)
                + "px)"
            )
        else:
            out.append("font-size: " + px(size))

    if style.get("weight") and style["weight"] != parent_style.get("weight"):
        out.append("font-weight: " + style["weight"])

    if style.get("lh") and style["lh"] != parent_style.get("lh"):
        out.append("line-height: " + str(style["lh"]))

    if style.get("ls"):
        out.append("letter-spacing: " + str(style["ls"]) + "px")

    if style.get("color") and style["color"] != parent_style.get("color"):
        out.append("color: " + css_color(style["color"]))

    if style.get("textAlign"):
        out.append("text-align: " + style["textAlign"])

    if style.get("transform"):
        out.append("text-transform: " + style["transform"])

    if style.get("underline"):
        out.append("text-decoration: underline")

    if style.get("listNone"):
        out.append("list-style: none")

    if display == "flex" and not style.get("dir"):
        out.append("min-width: 0")

    return out


def build_css(tree, data, source_url):
    """Return the stylesheet: base rules, one rule per element, then phones."""
    body_style = data.get("body") or {}

    background = usable(body_style.get("background"), "#FFFFFF")
    text_colour = usable(body_style.get("color"), "#1A1A1A")
    font_stack = body_style.get("fontFamily") or (
        "system-ui, -apple-system, 'Segoe UI', Arial, sans-serif"
    )
    size = int(body_style.get("size") or 17)
    line_height = round(float(body_style.get("lineHeight") or 1.6), 2)

    # The page colour goes on <html>, so it still reaches both edges when the
    # writing sits in a centred column.
    body_rules = []

    column = body_style.get("maxWidth") or 0
    if not column and body_style.get("centered"):
        column = body_style.get("width") or 0

    if column:
        body_rules.append("max-width: " + px(column))
        body_rules.append("margin-left: auto")
        body_rules.append("margin-right: auto")
    else:
        body_rules.append("margin: 0")

    if body_style.get("padding"):
        body_rules.append("padding: " + padding_value(body_style["padding"]))

    body_rules += [
        # A stray decorative strip must not create a sideways scrollbar.
        "overflow-x: hidden",
        "color: " + text_colour,
        "font-family: " + font_stack,
        "font-size: " + px(size),
        "line-height: " + str(line_height),
    ]

    lines = [
        "/* style.css",
        "   Rebuilt from " + source_url,
        "   Layout, spacing, colour and type were read from the live page.",
        "   Every rule below is named after the part it styles, in page order. */",
        "",
        "*,",
        "*::before,",
        "*::after {",
        INDENT + "box-sizing: border-box;",
        "}",
        "",
        "html {",
        INDENT + "background-color: " + background + ";",
        INDENT + "-webkit-text-size-adjust: 100%;",
        "}",
        "",
        "body {",
    ]

    lines += [INDENT + rule + ";" for rule in body_rules]

    lines += [
        "}",
        "",
        "img {",
        INDENT + "display: block;",
        INDENT + "max-width: 100%;",
        "}",
        "",
        "button {",
        INDENT + "font: inherit;",
        INDENT + "cursor: pointer;",
        "}",
        "",
        "a {",
        INDENT + "color: inherit;",
        INDENT + "text-decoration: none;",
        "}",
        "",
    ]

    # The rules themselves, top of the page first.
    rules = []
    compact = []       # rules that get tighter padding on small screens

    def walk(node, parent, depth):
        classes = node.get("class")
        if not classes or not node.get("tag"):
            return

        style = node.get("style") or {}
        decls = declarations(node, parent)

        if parent:
            parent_style = parent.get("style") or {}
            if parent_style.get("display") == "flex" and not parent_style.get("dir"):
                parent_width = parent.get("w") or 0
                width = node.get("w") or 0
                if parent_width and width:
                    share = round(width / parent_width * 100)
                    if 0 < share <= 100:
                        # Keep the original share of the row, but let a column
                        # grow when its neighbours wrap onto their own line.
                        decls.append("flex: 1 1 " + str(share) + "%")
                        decls.append("min-width: min(100%, " + px(width) + ")")

        if decls:
            rules.append("." + classes + " {")
            for decl in decls:
                rules.append(INDENT + decl + ";")
            rules.append("}")
            rules.append("")

        padding = style.get("pad")
        if depth <= 2 and padding and (padding[1] >= 24 or padding[3] >= 24):
            compact.append(
                "."
                + classes
                + " { padding-left: 18px; padding-right: 18px; }"
            )

        for child in node.get("kids", []):
            walk(child, node, depth + 1)

    for node in tree.get("nodes", []):
        walk(node, None, 0)

    lines += rules

    needs_nav, needs_menu = tree_flags(tree)

    if needs_nav:
        lines += [
            "/* ---------- navigation that folds into a button on a small screen ---------- */",
            "/* On a wide screen the wrapper adds no box, so the links sit exactly where",
            "   they did on the original page. */",
            ".nav-links { display: contents; }",
            "",
            ".nav-toggle {",
            INDENT + "display: none;",
            INDENT + "align-items: center;",
            INDENT + "gap: 8px;",
            INDENT + "padding: 10px 16px;",
            INDENT + "border: 1px solid currentColor;",
            INDENT + "border-radius: 999px;",
            INDENT + "background: transparent;",
            INDENT + "color: inherit;",
            INDENT + "font-size: 15px;",
            "}",
            "",
            "@media (max-width: 860px) {",
            INDENT + "[data-nav-toggle] .nav-links { display: none; }",
            INDENT + '[data-nav-toggle="true"] .nav-links { display: block; }',
            INDENT + "[data-nav-toggle] .nav-toggle { display: inline-flex; }",
            INDENT + "[data-nav-toggle] .nav-links > * { width: 100%; }",
            "}",
            "",
        ]

    if needs_menu:
        lines += [
            "/* ---------- menus that open and close ---------- */",
            "/* A panel ships hidden; script.js shows it when its button is pressed. */",
            "[hidden] {",
            INDENT + "display: none !important;",
            "}",
            "",
            "/* Whatever holds a panel is the anchor the panel opens from. */",
            "*:has(> .menu-panel) {",
            INDENT + "position: relative;",
            "}",
            "",
            ".menu-panel {",
            INDENT + "position: absolute;",
            INDENT + "top: 100%;",
            INDENT + "left: 0;",
            INDENT + "z-index: 20;",
            INDENT + "margin-top: 6px;",
            INDENT + "padding: 12px 16px;",
            INDENT + "width: max-content;",
            INDENT + "max-width: min(340px, calc(100vw - 32px));",
            INDENT + "max-height: 70vh;",
            INDENT + "overflow-y: auto;",
            INDENT + "border: 1px solid rgba(0, 0, 0, 0.15);",
            INDENT + "border-radius: 10px;",
            INDENT + "background: " + background + ";",
            INDENT + "color: " + text_colour + ";",
            INDENT + "box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);",
            INDENT + "text-align: left;",
            "}",
            "",
            ".menu-panel a {",
            INDENT + "display: block;",
            INDENT + "padding: 6px 0;",
            "}",
            "",
            "summary {",
            INDENT + "cursor: pointer;",
            "}",
            "",
        ]

    if compact:
        lines += [
            "/* Tighter side padding on a phone, so the text keeps a good measure. */",
            "@media (max-width: 700px) {",
        ]
        lines += [INDENT + rule for rule in compact]
        lines += ["}", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 5: write the JavaScript
# ---------------------------------------------------------------------------
SCRIPT = """// script.js
// The interactions a visitor can actually see and use on this page.
// Plain JavaScript, no libraries: read it, change it, keep it.

// ---------------------------------------------------------------------------
// 1. A link that points at a section of this page moves there smoothly.
// ---------------------------------------------------------------------------
document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    const target = document.querySelector(link.getAttribute("href"));
    if (!target) return;

    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

// ---------------------------------------------------------------------------
// 2. The navigation folds into a Menu button on a narrow screen.
//    style.css hides the links below 860px and script.js opens them again.
// ---------------------------------------------------------------------------
document.querySelectorAll("[data-nav-button]").forEach((button) => {
  const nav = button.closest("[data-nav-toggle]");
  if (!nav) return;

  const close = () => {
    nav.setAttribute("data-nav-toggle", "false");
    button.setAttribute("aria-expanded", "false");
    button.textContent = "Menu";
  };

  button.addEventListener("click", () => {
    const open = nav.getAttribute("data-nav-toggle") === "true";

    nav.setAttribute("data-nav-toggle", open ? "false" : "true");
    button.setAttribute("aria-expanded", open ? "false" : "true");
    button.textContent = open ? "Menu" : "Close";
  });

  // Following a link closes the menu, so the section is visible straight away.
  nav.querySelectorAll(".nav-links a").forEach((link) => {
    link.addEventListener("click", close);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
});

// ---------------------------------------------------------------------------
// 3. A menu button opens and closes the panel it controls.
//    The panel starts hidden; the button carries aria-expanded for screen readers.
// ---------------------------------------------------------------------------
document.querySelectorAll("[data-menu]").forEach((button) => {
  const panel = document.getElementById(button.getAttribute("data-menu"));
  if (!panel) return;

  const close = () => {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
  };

  button.addEventListener("click", (event) => {
    event.preventDefault();

    const open = !panel.hidden;
    panel.hidden = open;
    button.setAttribute("aria-expanded", open ? "false" : "true");
  });

  // Escape, or a click anywhere outside, closes the menu again.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });

  document.addEventListener("click", (event) => {
    if (!panel.contains(event.target) && !button.contains(event.target)) close();
  });
});

// ---------------------------------------------------------------------------
// 4. A picture that could not be copied is hidden instead of leaving a gap.
// ---------------------------------------------------------------------------
document.querySelectorAll("img").forEach((image) => {
  image.addEventListener("error", () => {
    image.style.visibility = "hidden";
  });
});
"""


def build_js(tree):
    """Return the script as text."""
    return SCRIPT


# ---------------------------------------------------------------------------
# Step 6: put it all on disk
# ---------------------------------------------------------------------------
def build_site(extracted, folder, source_url="", screenshot=None):
    """Write index.html, style.css, script.js and assets/ into folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    extracted = extracted or {}
    tree = {"nodes": extracted.get("nodes") or []}

    if not tree["nodes"]:
        raise ValueError("The page had no visible elements to rebuild.")

    saved = download_assets(tree, folder / "assets" / "images")

    html_text = build_html(tree, extracted, source_url, saved)
    css_text = build_css(tree, extracted, source_url)
    js_text = build_js(tree)

    html_file = folder / "index.html"
    css_file = folder / "style.css"
    js_file = folder / "script.js"

    html_file.write_text(html_text, encoding="utf-8")
    css_file.write_text(css_text, encoding="utf-8")
    js_file.write_text(js_text, encoding="utf-8")

    # A screenshot is kept only so you can compare your edit with the original.
    reference = None
    if screenshot and Path(screenshot).exists():
        reference_folder = folder / "reference"
        reference_folder.mkdir(exist_ok=True)
        reference = reference_folder / "screenshot.png"
        shutil.copy2(screenshot, reference)

    return {
        "folder": folder,
        "html": html_text,
        "css": css_text,
        "js": js_text,
        "html_file": html_file,
        "css_file": css_file,
        "js_file": js_file,
        "assets": sorted(
            (folder / relative) for relative in saved.values()
        ),
        "asset_map": saved,
        "reference": reference,
        "elements": count_nodes({"kids": tree["nodes"]}),
    }
