# scripting.py
# Step 9: the smallest useful script for our rebuilt pages.
# One job: the button in the header switches between the light page and a dark one.

SCRIPT = """// script.js
// One job: when the button is clicked, switch the page between light and dark.

const button = document.getElementById("theme-toggle");

// If the button is missing, do nothing instead of crashing the page.
if (button) {
  button.addEventListener("click", () => {
    // classList.toggle adds "dark" the first time and removes it the next time.
    const isDark = document.body.classList.toggle("dark");

    // The label always offers the mode you are not using right now.
    button.textContent = isDark ? "Light mode" : "Dark mode";
  });
}
"""


def build_js():
    """Return the whole script as one string."""
    return SCRIPT
