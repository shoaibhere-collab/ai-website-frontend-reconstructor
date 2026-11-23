# AI Website Frontend Reconstructor

Analyse any public web page, then rebuild it as a clean, static frontend you own —
HTML, CSS and JavaScript — using a real browser to read the live page rather than
guessing from its HTML source.

Two ways to use it:

- **Web interface** (`streamlit_app.py`) — a workspace with a URL command bar, live
  analysis, side-by-side original/rebuilt previews, desktop/tablet/mobile check, and
  a Figma handoff export.
- **Command line** (`app.py`) — the same pipeline in a terminal, which is useful for
  scripting or debugging.

## Requirements

- **Python 3.9+** (developed on 3.15)
- **Chromium** via Playwright, downloaded once (see below)
- Windows, macOS or Linux

## Install

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell / cmd)
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. Install the Python packages
pip install -r requirements.txt

# 3. Download the browser Playwright drives
python -m playwright install chromium

# 4. Optional: confirm the environment is ready
python check_setup.py
```

## Run the web interface

Start the server from this folder:

```bash
streamlit run streamlit_app.py --server.port 8501
```

It prints a line like `You can now view your Streamlit app in your browser` followed by
`URL: http://127.0.0.1:8501`. Open that address — **[http://localhost:8501](http://localhost:8501)** —
paste a URL such as `https://www.w3.org` and press **Analyze page**. A run takes roughly
20–60 seconds depending on the page.

> **The address only works while the server is running.** `localhost` is not a website —
it means "this computer". Two consequences:
>
> - Clicking `http://localhost:8501` from a GitHub page, an email or a document does
>   nothing useful unless you have already started the server on your own machine.
> - When you close the terminal window running `streamlit`, the app stops and the page
>   will refuse to connect. Start it again with the command above.
>
> If the command runs but the browser will not connect, check the terminal: a startup
error there (a missing package, port already in use) is the reason.

### If the port is already in use

Another copy is still running. Either use it at <http://localhost:8501>, or stop it:

```bash
# Windows
netstat -ano | findstr :8501
taskkill /PID <pid> /F
# macOS / Linux
lsof -ti:8501 | xargs kill
```

Or start on a different port with `--server.port 8502` and open that address instead.

To reach the app from other devices on your network, add `--server.address 0.0.0.0` and
use your machine's LAN IP. Binding to `127.0.0.1` (the safer default) restricts access
to this machine only.

## Run the command line

```bash
python app.py
```

It asks for a URL, shows what it finds, and writes the rebuilt site to
`output/<domain>/`. Set `HEADLESS = True` near the top of `app.py` to run the
browser invisibly.

## What a run produces

| Path | Contents |
| --- | --- |
| `output/<domain>/` | Rebuilt site: `index.html`, `style.css`, `script.js`, copied assets |
| `data/<domain>.json` | Page structure and design tokens captured from the live site |
| `screenshots/<domain>.png` | Screenshot of the original page |

`output/`, `data/` and `screenshots/` are generated at runtime and are **not**
tracked by Git.

## How it works

| Module | Role |
| --- | --- |
| `analyse.py` | Loads the page and extracts headings, text, images and colours |
| `ai.py` | Turns the extracted structure into a layout plan |
| `reconstruct.py` | Builds sections from the plan |
| `styling.py` | Derives the colour palette and typography |
| `scripting.py` | Writes the small amount of JavaScript the page needs |
| `assets.py` | Downloads and stores the page's images and fonts |
| `build.py` | Emits the final HTML/CSS/JS files |
| `preview.py` | Inlines assets so the rebuilt page can be previewed offline |
| `streamlit_app.py`, `ui.css` | The web interface |

## Notes and limitations

- Only publicly reachable `http://` and `https://` pages are supported.
- Pages that render entirely behind a login or heavy anti-bot protection will not
  reconstruct successfully.
- The rebuilt frontend is a static approximation of the original layout and styling;
  interactive behaviour beyond menus and simple toggles is not reproduced.
- The Figma export produces a handoff package (design-token JSON, `FIGMA.md` and a
  ZIP of the build) rather than a native `.fig` file.

## License

No license has been chosen yet.
