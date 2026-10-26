"""Rebuild an archify diagram's .png from its .json source.

Usage (from the repo root): python docs/diagrams/render_archify.py <name> [<name> ...]
Needs node, the archify skill (~/.claude/skills/archify), google-chrome and Pillow.
The PNG is a 2x headless-Chrome screenshot cropped to the title bar plus the diagram card.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

OUT = Path("docs/diagrams")
ARCHIFY = Path.home() / ".claude/skills/archify/bin/archify.mjs"
FOLDERS = {"development-overview-v2": "development-overview"}  # boards that share another diagram's folder
TYPES = {"guardrails-pipeline": "dataflow", "rag-evals-pipeline": "dataflow", "triage-approval-flow": "sequence", "claim-sequence": "sequence"}


def crop_to_card(shot: Path, dest: Path) -> None:
    """Cut the screenshot at the bottom edge of the diagram card (the first non-white run below it)."""
    im = Image.open(shot).convert("RGB")
    xs = (100, 140, 200, 260)
    y = 300
    while y < im.height - 4 and not all(im.getpixel((x, y))[0] < 250 and im.getpixel((x, y + 3))[0] < 250 for x in xs):
        y += 1
    im.crop((0, 0, im.width, y + 10)).save(dest, optimize=True)


def render(name: str) -> None:
    kind = TYPES.get(name, "architecture")
    folder = OUT / FOLDERS.get(name, name)
    with tempfile.TemporaryDirectory() as tmp:
        html, shot = Path(tmp) / f"{name}.html", Path(tmp) / "full.png"
        subprocess.run(
            [
                "node",
                str(ARCHIFY),
                "finalize",
                kind,
                str(folder / f"{name}.json"),
                str(html),
                "--repo-root",
                ".",
                "--quality",
                "showcase",
            ],
            check=True,
        )
        subprocess.run(
            [
                "google-chrome",
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--force-device-scale-factor=2",
                "--window-size=1400,4200",
                f"--screenshot={shot}",
                html.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        crop_to_card(shot, folder / f"{name}.png")


if __name__ == "__main__":
    for diagram in sys.argv[1:]:
        render(diagram)
