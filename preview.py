# preview.py
# Step 11: open the finished page in the default browser.

import webbrowser
from pathlib import Path


def page_address(html_file):
    """Turn output/example.com/index.html into a browser address."""
    return Path(html_file).resolve().as_uri()


def open_page(html_file):
    """Open the finished page in the default browser. Returns the address."""
    address = page_address(html_file)
    opened = webbrowser.open(address)

    if not opened:
        print("No browser could be opened automatically.")
        print("Copy this address into your browser instead:")
        print("   ", address)

    return address
