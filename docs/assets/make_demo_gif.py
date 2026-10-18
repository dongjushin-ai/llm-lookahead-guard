"""Render docs/assets/demo.gif from the real output of the CLI.

Every line shown in the GIF is captured by running the commands below. The
terminal is drawn as HTML, screenshotted frame by frame with Playwright
(Chromium) and joined with ffmpeg.

    pip install playwright && python -m playwright install chromium   # once
    python docs/assets/make_demo_gif.py
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "demo.gif"

LOG = [
    {"id": "nvda-0301", "as_of": "2023-03-01", "model": "gpt-4o-2024-08-06", "horizon_days": 20,
     "prompt": "Date: 2023-03-01. Ticker: NVDA. Last close 232.10, RSI 58. Decide BUY or SELL for the next 20 trading days."},
    {"id": "aapl-0503", "as_of": "2023-05-03", "model": "claude-3-5-sonnet-20241022", "horizon_days": 5,
     "prompt": "Apple (AAPL) reports earnings on May 4, 2023. Last close 167.45. BUY or SELL into the print?"},
]

# (command shown, argv to run, keep only lines matching this regex or None)
SCENES = [
    [("lookahead-guard check backtest.jsonl", ["lookahead-guard", "check", "backtest.jsonl"], None)],
    [("lookahead-guard mask backtest.jsonl > masked.jsonl", None, None),
     ("lookahead-guard check masked.jsonl", ["lookahead-guard", "check", "masked.jsonl"], None),
     ("python examples/ab_demo.py", [sys.executable, str(ROOT / "examples" / "ab_demo.py")], r"Direction accuracy|n=\d+")],
]

CSS = """
body { margin: 0; background: #ffffff; }
.win { width: 1000px; height: 640px; margin: 0; background: #0d1117; border-radius: 0; overflow: hidden;
       font-family: 'DejaVu Sans Mono', monospace; }
.bar { height: 30px; background: #161b22; display: flex; align-items: center; padding: 0 12px; gap: 8px;
       color: #8b949e; font: 13px 'DejaVu Sans', sans-serif; }
.dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
pre { margin: 0; padding: 12px 16px; color: #c9d1d9; font-size: 13.2px; line-height: 1.38;
      white-space: pre-wrap; word-break: break-word; }
.p { color: #3fb950; } .c { color: #f0f6fc; font-weight: bold; } .e { color: #ff7b72; font-weight: bold; }
.w { color: #d29922; font-weight: bold; } .h { color: #79c0ff; } .d { color: #8b949e; } .ok { color: #3fb950; font-weight: bold; }
.cur { background: #c9d1d9; color: #0d1117; }
"""


def run(argv, cwd):
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return proc.stdout.rstrip("\n").splitlines(), proc.returncode


def colour(line: str) -> str:
    s = html.escape(line)
    if re.match(r"\s+ERROR ", line):
        return re.sub(r"ERROR", '<span class="e">ERROR</span>', s, count=1)
    if re.match(r"\s+WARN ", line):
        return re.sub(r"WARN", '<span class="w">WARN</span>', s, count=1)
    if re.match(r"\S+\.jsonl:\d+ ", line):
        return f'<span class="h">{s}</span>'
    if line.lstrip().startswith(">"):
        return f'<span class="d">{s}</span>'
    if "0 with errors" in line:
        return f'<span class="ok">{s}</span>'
    if re.search(r"[1-9]\d* with errors", line):
        return f'<span class="e">{s}</span>'
    if re.search(r"gap=", line):
        return re.sub(r"(gap=\S+)", r'<span class="e">\1</span>', s)
    return s


def build_frames(workdir: Path):
    """Return a list of (html_body, seconds)."""
    (workdir / "backtest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in LOG), encoding="utf-8")
    frames = []
    for scene in SCENES:
        screen: list[str] = []
        for cmd, argv, keep in scene:
            if argv is None:  # the mask step: run it for real, it prints nothing
                out, _ = run(["lookahead-guard", "mask", "backtest.jsonl"], workdir)
                (workdir / "masked.jsonl").write_text("\n".join(out) + "\n", encoding="utf-8")
                lines, code = [], 0
            else:
                lines, code = run(argv, workdir)
                if keep:
                    lines = [ln for ln in lines if re.search(keep, ln)]
            for i in range(0, len(cmd) + 1, 3):  # typing
                frames.append((screen + [f'<span class="p">$</span> <span class="c">{html.escape(cmd[:i])}</span><span class="cur"> </span>'], 0.045))
            screen = screen + [f'<span class="p">$</span> <span class="c">{html.escape(cmd)}</span>']
            frames.append((screen + ['<span class="cur"> </span>'], 0.35))
            body = [colour(ln) for ln in lines]
            for j in range(0, len(body), 4):  # output appears in chunks
                frames.append((screen + body[: j + 4], 0.07))
            screen = screen + body
            if argv and argv[0] == "lookahead-guard":
                screen = screen + [f'<span class="d"># exit code {code}</span>']
            frames.append((screen + [""], 0.2))
        hold = 3.4 if scene is SCENES[0] else 4.0
        frames.append((screen + ['<span class="p">$</span> <span class="cur"> </span>'], hold))
    return frames


def main() -> int:
    from playwright.sync_api import sync_playwright

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg is required", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        frames = build_frames(tmp)
        shots = tmp / "shots"
        shots.mkdir()
        page_html = (f"<html><head><style>{CSS}</style></head><body><div class='win'><div class='bar'>"
                     "<span class='dot' style='background:#ff5f56'></span><span class='dot' style='background:#ffbd2e'></span>"
                     "<span class='dot' style='background:#27c93f'></span>&nbsp; llm-lookahead-guard</div><pre id='t'></pre></div></body></html>")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1000, "height": 640})
            page.set_content(page_html)
            for n, (lines, _) in enumerate(frames):
                page.evaluate("h => { document.getElementById('t').innerHTML = h; }", "\n".join(lines))
                page.screenshot(path=str(shots / f"f{n:04d}.png"))
            browser.close()
        concat = tmp / "list.txt"
        with open(concat, "w") as fh:
            for n, (_, secs) in enumerate(frames):
                fh.write(f"file '{shots / f'f{n:04d}.png'}'\nduration {secs}\n")
            fh.write(f"file '{shots / f'f{len(frames) - 1:04d}.png'}'\n")
        total = sum(s for _, s in frames)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
                        "-vf", "fps=25,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=none",
                        "-loop", "0", str(OUT)], check=True)
        if os.environ.get("KEEP_FRAMES"):
            shutil.copytree(shots, os.environ["KEEP_FRAMES"], dirs_exist_ok=True)
    print(f"{OUT.relative_to(ROOT)}: {len(frames)} frames, {total:.1f}s, {OUT.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
