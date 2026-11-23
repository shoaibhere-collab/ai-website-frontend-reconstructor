# ai.py
# Step 6: ask an AI service for better section names and page copy.
# Without an API key this file still works: it builds the same kind of plan
# from the page itself, so later steps never need to know the difference.

import json
import os
import urllib.error
import urllib.request

# --- The AI service ------------------------------------------------------
# These three lines are the only place a provider is named.
# Any OpenAI-compatible service works; change them and nothing else:
#   Groq      https://api.groq.com/openai/v1/chat/completions
#   Gemini    https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
#   OpenAI    https://api.openai.com/v1/chat/completions
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"
API_KEY_ENV = "OPENROUTER_API_KEY"

TIMEOUT = 60          # seconds to wait for an answer
MAX_SECTIONS = 5
MAX_HEADING_CHARS = 50
MAX_BODY_WORDS = 40


class AiError(Exception):
    """Something went wrong while talking to the AI service."""


def tidy(text):
    """Squash runs of spaces, tabs and newlines into single spaces."""
    return " ".join(text.split())


def first_sentence(text, limit=140):
    """Return the first sentence of a text, shortened to limit characters."""
    text = tidy(text)
    cut = text.find(". ")

    if cut != -1:
        text = text[: cut + 1]

    return text[:limit].strip()


def summary_for_prompt(summary):
    """Write the clean summary as short plain text for the AI to read."""
    lines = [
        "Page title: " + summary.get("title", ""),
        "Main heading: " + summary.get("main_heading", ""),
        "",
        "Headings in visual order:",
    ]

    for heading in summary.get("headings", [])[:15]:
        lines.append("- h" + str(heading.get("level", 0)) + ": " + heading.get("text", ""))

    lines.append("")
    lines.append("Body paragraphs:")

    for paragraph in summary.get("paragraphs", [])[:8]:
        lines.append("- " + paragraph[:300])

    return "\n".join(lines)


def build_prompt(summary):
    """The instructions we send, plus the summary of the page."""
    instructions = (
        "You are helping rebuild the front end of a web page.\n"
        "Below is a summary of the original page. Write a short page plan for a\n"
        "page with the same subject.\n\n"
        "Return JSON with exactly these keys:\n"
        '- "title": one short page title (max 60 characters)\n'
        '- "tagline": one sentence shown under the title (max 140 characters)\n'
        '- "sections": 3 to 5 objects, each with "heading" and "body"\n'
        "  - heading: a short section name (max 50 characters)\n"
        "  - body: one or two plain sentences (max 40 words)\n\n"
        "Rules: keep the same subject and meaning as the original. Do not invent\n"
        "facts, prices, names or claims. Do not use markdown. Answer with JSON only.\n\n"
        'Shape: {"title": "...", "tagline": "...", "sections": '
        '[{"heading": "...", "body": "..."}]}\n\n'
        "Page summary:\n"
    )

    return instructions + summary_for_prompt(summary)


def ask_ai(key, prompt):
    """Send the prompt to the AI service and return its text answer."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:200]
        raise AiError("The service refused the request (" + str(error.code) + "). " + detail)
    except urllib.error.URLError as error:
        raise AiError("Could not reach the service: " + str(error.reason))
    except TimeoutError:
        raise AiError("The service took too long to answer.")

    try:
        answer = json.loads(raw)
        return answer["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        raise AiError("The service sent an answer in an unexpected shape.")


def validate_plan(data):
    """Check that the AI answered in the shape we asked for."""
    if not isinstance(data, dict):
        raise AiError("The answer was not a JSON object.")

    title = tidy(str(data.get("title", "")))
    tagline = tidy(str(data.get("tagline", "")))
    raw_sections = data.get("sections", [])

    if not title or not isinstance(raw_sections, list) or not raw_sections:
        raise AiError("The answer had no title or no sections.")

    sections = []

    for item in raw_sections[:MAX_SECTIONS]:
        if not isinstance(item, dict):
            continue

        heading = tidy(str(item.get("heading", "")))
        body = tidy(str(item.get("body", "")))

        if not heading:
            continue

        sections.append({"heading": heading[:MAX_HEADING_CHARS], "body": body})

    if not sections:
        raise AiError("The answer had no usable sections.")

    return {"title": title, "tagline": tagline, "sections": sections}


def parse_plan(text):
    """Turn the AI's text answer into a plan dictionary."""
    cleaned = text.strip()

    if "```" in cleaned:                      # models like to wrap JSON in code fences
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise AiError("The answer did not contain any JSON.")

    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        raise AiError("The answer was not valid JSON.")

    return validate_plan(data)


def offline_plan(summary):
    """Build a plan from the page itself, with no AI involved."""
    title = summary.get("main_heading") or summary.get("title") or "Untitled page"
    paragraphs = summary.get("paragraphs", [])

    tagline = first_sentence(paragraphs[0]) if paragraphs else ""

    # The first paragraph became the tagline, so sections start from the next one.
    remaining = paragraphs[1:] if len(paragraphs) > 1 else paragraphs

    headings = [item for item in summary.get("headings", []) if item.get("text")]

    # The first heading is the page title, already used above.
    if headings and headings[0]["text"].lower() == title.lower():
        headings = headings[1:]

    sections = []

    for index, heading in enumerate(headings[:MAX_SECTIONS]):
        body = ""

        if index < len(remaining):
            body = first_sentence(remaining[index], limit=200)

        if not body:
            body = "No separate paragraph was found for this section."

        sections.append({"heading": heading["text"][:MAX_HEADING_CHARS], "body": body})

    if not sections:
        body = ""
        if len(remaining) > 1:
            body = first_sentence(remaining[1], limit=200)
        elif remaining:
            # Only one paragraph: show a little more of it than the tagline does.
            body = first_sentence(remaining[0], limit=200)

        sections = [{"heading": title[:MAX_HEADING_CHARS], "body": body or tagline or "Page content."}]

    return {"title": title, "tagline": tagline, "sections": sections}


def make_plan(summary):
    """Return a page plan, using AI when a key is available."""
    key = os.environ.get(API_KEY_ENV, "").strip()

    if not key:
        plan = offline_plan(summary)
        plan["mode"] = "offline"
        plan["note"] = "No " + API_KEY_ENV + " key found, so the page itself was used."
        return plan

    try:
        reply = ask_ai(key, build_prompt(summary))
        plan = parse_plan(reply)
        plan["mode"] = "ai"
        plan["note"] = "Copy written by " + MODEL
        return plan
    except AiError as error:
        plan = offline_plan(summary)
        plan["mode"] = "offline"
        plan["note"] = "AI was not used: " + str(error)
        return plan
