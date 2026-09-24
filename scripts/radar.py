#!/usr/bin/env python3
"""
radar.py - Render spider / radar charts as standalone animated SVGs. Stdlib only.
Personalized for Angel Pino (@AngelitUX) with Purple & Orange retro-tech palette.

Sources of data:
  1. A local JSON file:
        python scripts/radar.py --data assets/skills.json -o assets/radar
        python scripts/radar.py --data assets/langmix.json -o assets/radar-langs --values

  2. Live GitHub language stats:
        python scripts/radar.py --github AngelitUX -o assets/radar-langs

Writes <out>-dark.svg and <out>-light.svg so GitHub README can switch via <picture>.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Retro-Tech Purple & Orange Theme
THEMES = {
    "dark": {
        "grid": "#3a2554",
        "spoke": "#2b1c40",
        "label": "#f3f5f9",
        "value": "#ffaa1a",
        "title": "#d884ff",
        "fill": "#9d4edd",
        "stroke": "#ff7a00",
        "vertex": "#ffa200",
        "bg": "none",
    },
    "light": {
        "grid": "#dcd0f4",
        "spoke": "#e8def7",
        "label": "#130626",
        "value": "#d9480f",
        "title": "#480ca8",
        "fill": "#7b2cbf",
        "stroke": "#e85d04",
        "vertex": "#f48c06",
        "bg": "none",
    },
}

UA = {"User-Agent": "radar.py"}


def from_json(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    axes = [(a["label"], float(a["value"])) for a in d["axes"]]
    return d.get("title", "Skill Radar"), axes


def _api(url, token):
    req = urllib.request.Request(url, headers=dict(UA))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def from_github(user: str, token: str | None, limit: int, exclude: set[str], curve: float):
    totals: dict[str, int] = {}
    page = 1
    while True:
        repos = _api(
            f"https://api.github.com/users/{user}/repos?per_page=100&page={page}&type=owner&sort=pushed",
            token,
        )
        if not repos:
            break
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            try:
                langs = _api(repo["languages_url"], token)
            except urllib.error.HTTPError:
                continue
            for name, count in langs.items():
                if name.lower() in exclude:
                    continue
                totals[name] = totals.get(name, 0) + count
        if len(repos) < 100:
            break
        page += 1

    if not totals:
        sys.exit(f"no language data found for '{user}' (private repos need a token)")

    top = sorted(totals.items(), key=lambda kv: -kv[1])[:limit]
    peak = top[0][1]
    axes = [(n, round(100 * (c / peak) ** curve, 1)) for n, c in top]
    return f"{user} · language mix", axes


FONT = "ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
LBL, VAL, TTL = 16.0, 15.0, 20.0


def ring(radius, n, start=-math.pi / 2):
    return [
        (radius * math.cos(start + i * 2 * math.pi / n),
         radius * math.sin(start + i * 2 * math.pi / n))
        for i in range(n)
    ]


def text_width(s: str, font_size: float) -> float:
    return len(s) * font_size * 0.61


def split_label(label: str) -> list[str]:
    """Split label into compact lines if long to prevent SVG width inflation on GitHub."""
    if " & " in label and len(label) > 15:
        p = label.split(" & ")
        return [p[0] + " &", p[1]]
    if " / " in label and len(label) > 13:
        p = label.split(" / ")
        return [p[0] + " /", p[1]]
    return [label]


def render(title, axes, theme: str, size: int, rings: int, show_values: bool, animate: bool) -> str:
    c = THEMES[theme]
    n = len(axes)
    r = size / 2 - 8
    gap = 24

    vals = [max(0.0, min(100.0, v)) for _, v in axes]
    outer = ring(r, n)

    labels = []
    for i, (label, _) in enumerate(axes):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        cosv, sinv = math.cos(ang), math.sin(ang)
        lx, ly = (r + gap) * cosv, (r + gap) * sinv
        anchor = "middle" if abs(cosv) < 0.28 else ("start" if cosv > 0 else "end")
        dy = 4 if abs(sinv) < 0.25 else (14 if sinv > 0 else -6)
        lines = split_label(label)
        labels.append((lx, ly + dy, anchor, lines, vals[i]))

    minx, maxx, miny, maxy = -r, r, -r, r
    line_h = LBL * 1.2
    for lx, ly, anchor, lines, v in labels:
        max_w = max(text_width(line, LBL) for line in lines)
        if show_values:
            max_w = max(max_w, text_width(f"{v:g}", VAL))
        if anchor == "start":
            x0, x1 = lx, lx + max_w
        elif anchor == "end":
            x0, x1 = lx - max_w, lx
        else:
            x0, x1 = lx - max_w / 2, lx + max_w / 2
        y0 = ly - LBL
        y1 = ly + (len(lines) - 1) * line_h + 4 + (VAL + 4 if show_values else 0)
        minx, maxx = min(minx, x0), max(maxx, x1)
        miny, maxy = min(miny, y0), max(maxy, y1)

    pad = 12
    title_h = TTL + 16 if title else 0
    W = round((maxx - minx) + 2 * pad)
    H = round((maxy - miny) + 2 * pad + title_h)
    ox, oy = -minx + pad, -miny + pad + title_h

    if title:
        need = round(text_width(title, TTL) + 2 * pad)
        if need > W:
            ox += (need - W) / 2
            W = need

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="{esc(title) or "radar chart"}" font-family="{FONT}">'
    ]
    if c["bg"] != "none":
        parts.append(f'<rect width="100%" height="100%" fill="{c["bg"]}"/>')
    if title:
        parts.append(
            f'<text x="{W / 2:.1f}" y="{pad + TTL:.0f}" text-anchor="middle" '
            f'font-size="{TTL}" font-weight="800" fill="{c["title"]}">'
            f'{esc(title)}</text>'
        )
    parts.append(f'<g transform="translate({ox:.1f},{oy:.1f})">')

    # Concentric rings
    for k in range(rings, 0, -1):
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in ring(r * k / rings, n))
        parts.append(
            f'<polygon points="{d}" fill="none" stroke="{c["grid"]}" '
            f'stroke-width="1.2" opacity="{0.40 + 0.5 * k / rings:.2f}"/>'
        )

    # Spokes
    for x, y in outer:
        parts.append(
            f'<line x1="0" y1="0" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="{c["spoke"]}" stroke-width="1.2"/>'
        )

    # Data shape
    shape = [(px * v / 100, py * v / 100) for (px, py), v in zip(outer, vals)]
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in shape)
    parts.append("<g>")
    if animate:
        parts.append(
            '<animateTransform attributeName="transform" type="scale" '
            'values="0.04;1" dur="1.1s" calcMode="spline" keyTimes="0;1" '
            'keySplines="0.22 1 0.36 1" fill="freeze"/>'
        )
    parts.append(
        f'<polygon points="{d}" fill="{c["fill"]}" fill-opacity="0.28" '
        f'stroke="{c["stroke"]}" stroke-width="2.6" stroke-linejoin="round"/>'
    )
    for x, y in shape:
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.0" fill="{c["vertex"]}" '
            f'stroke="{c["stroke"]}" stroke-width="1.4"/>'
        )
    parts.append("</g>")

    # Axis labels (multiline support with increased font size)
    for lx, ly, anchor, lines, v in labels:
        base_y = ly
        for line_idx, line in enumerate(lines):
            curr_y = base_y + line_idx * line_h
            parts.append(
                f'<text x="{lx:.1f}" y="{curr_y:.1f}" text-anchor="{anchor}" '
                f'font-size="{LBL}" font-weight="700" fill="{c["label"]}">'
                f'{esc(line)}</text>'
            )
        if show_values:
            val_y = base_y + (len(lines) - 1) * line_h + VAL + 4
            parts.append(
                f'<text x="{lx:.1f}" y="{val_y:.1f}" text-anchor="{anchor}" '
                f'font-size="{VAL}" font-weight="700" fill="{c["value"]}">{v:g}</text>'
            )

    parts.append("</g></svg>")
    return "".join(parts)


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--data", type=Path, default=Path("assets/skills.json"))
    src.add_argument("--github", metavar="USER",
                     help="build the radar from GitHub language stats instead")
    p.add_argument("-o", "--out", type=Path, default=Path("assets/radar"),
                   help="output path WITHOUT extension")
    p.add_argument("--title", help="override the chart title ('' for none)")
    p.add_argument("--size", type=int, default=320)
    p.add_argument("--rings", type=int, default=4)
    p.add_argument("--limit", type=int, default=7,
                   help="max languages if pulling from GitHub (default: 7)")
    p.add_argument("--exclude", default="html,css,jupyter notebook",
                   help="comma-separated languages to drop from GitHub stats")
    p.add_argument("--curve", type=float, default=0.55,
                   help="power curve for GitHub stats to prevent the #1 lang from flattening the rest")
    p.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),
                   help="GitHub API token (optional; reads GITHUB_TOKEN env var)")
    p.add_argument("--values", action="store_true",
                   help="print numeric value below each label")
    p.add_argument("--no-animate", dest="animate", action="store_false",
                   help="skip the pulse-in SMIL animation")
    p.set_defaults(animate=True)

    args = p.parse_args(argv)

    if args.github:
        exclude = {x.strip().lower() for x in args.exclude.split(",") if x.strip()}
        title, axes = from_github(args.github, args.token, args.limit, exclude, args.curve)
    else:
        title, axes = from_json(args.data)

    if args.title is not None:
        title = args.title

    out_base = args.out
    out_base.parent.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        svg = render(title, axes, theme=theme, size=args.size, rings=args.rings,
                     show_values=args.values, animate=args.animate)
        target = out_base.parent / f"{out_base.name}-{theme}.svg"
        target.write_text(svg, encoding="utf-8")
        print(f"wrote {target}  ({len(axes)} axes)")


if __name__ == "__main__":
    main()
