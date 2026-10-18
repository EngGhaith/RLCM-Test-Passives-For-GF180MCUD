#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Regenerate every picture in docs/img from the layout files in this repository.

Run from anywhere inside a clone:

    uv run docs/scripts/update_images.py

See docs/updating-images.md for the requirements and for what each step does.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
IMG = REPO / "docs" / "img"
BUILD = REPO / "build"

ZIP = REPO / "RLCMV4_filled.zip"
GDS_NAME = "RLCMV4_filled.gds"
SEPARATE = REPO / "seperate_GDSs"

BACKGROUND = (0x10, 0x16, 0x1C)
WHITE = (255, 255, 255)
# Must match LAYERS in render_layout.py.
LEGEND = [
    ("Metal5", (0xD9, 0xC2, 0x7A)),
    ("Metal4", (0xC9, 0x72, 0x2E)),
    ("Metal3", (0x5E, 0x9E, 0x3E)),
    ("Metal2", (0x2A, 0xA1, 0x98)),
    ("Metal1", (0x3A, 0x5F, 0xCD)),
    ("MIM top plate", (0xC0, 0x4F, 0xC0)),
    ("Port marker", (0xFF, 0x30, 0x30)),
    ("Pad opening", None),
]

FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"), Path("/Library/Fonts")]


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        if (d / name).exists():
            return ImageFont.truetype(str(d / name), size)
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# What is on the die. Coordinates are µm in the top cell of RLCMV4_filled.gds.
# "box" outlines the structure on the whole-die picture and "label" is where
# its number is drawn.
# ---------------------------------------------------------------------------
STRUCTURES = [
    {"id": "1", "name": "MIM capacitor, 100 µm × 100 µm", "box": (636, 379, 748, 491), "label": (540, 440)},
    {"id": "2", "name": "MIM capacitor, 54 µm × 25 µm", "box": (1211, 379, 1277, 416), "label": (1370, 440)},
    {"id": "3", "name": "Transformer, one turn per winding", "box": (819, 664, 1117, 962), "label": (968, 1090)},
    {"id": "4", "name": "Three-line thru", "box": (473, 1400, 1463, 1746), "label": (968, 1850)},
    {"id": "5", "name": "Transformer, two turns per winding", "box": (819, 2184, 1117, 2482), "label": (968, 2060)},
    {"id": "6", "name": "Three-port launch, signals joined", "box": (26, 2755, 499, 3431), "label": (610, 3093)},
    {"id": "7", "name": "Three-port launch, signals open", "box": (1437, 2755, 1910, 3431), "label": (1326, 3093)},
    {"id": "8", "name": "Spiral inductor, four turns", "box": (1285, 3628, 1583, 3926), "label": (1170, 3777)},
    {"id": "9", "name": "Symmetric inductor with centre tap", "box": (462, 4160, 760, 4458), "label": (875, 4309)},
    {"id": "10", "name": "Spiral inductor, two turns", "box": (1285, 4236, 1583, 4534), "label": (1170, 4385)},
    {"id": "11", "name": "Two-port launch, signals joined", "box": (430, 4731, 954, 5096), "label": (692, 4630)},
    {"id": "12", "name": "Two-port launch, signals open", "box": (982, 4757, 1506, 5096), "label": (1244, 4630)},
    {"id": "13", "name": "Three unconnected bond pads", "box": (20, 3509, 98, 3893), "label": (230, 3701)},
]

# Probe launches: (structure ids, die edge, range along that edge in µm, number of signal pads).
LAUNCHES = [
    ("1", "bottom", (430, 954), 2),
    ("2", "bottom", (982, 1506), 2),
    ("3", "left", (475, 1151), 3),
    ("3", "right", (475, 1151), 3),
    ("4", "left", (1235, 1911), 3),
    ("4", "right", (1235, 1911), 3),
    ("5", "left", (1995, 2671), 3),
    ("5", "right", (1995, 2671), 3),
    ("6", "left", (2755, 3431), 3),
    ("7", "right", (2755, 3431), 3),
    ("8", "right", (3515, 4039), 2),
    ("9", "left", (3971, 4647), 3),
    ("10", "right", (4123, 4647), 2),
    ("11", "top", (430, 954), 2),
    ("12", "top", (982, 1506), 2),
]

ROLE_COLOURS = {
    "G": (0x8A, 0x93, 0x9C),
    "S1": (0x4F, 0x9D, 0xFF),
    "S2": (0xFF, 0xB0, 0x3A),
    "S3": (0x5F, 0xD0, 0x6A),
    "NC": None,
}


def run(cmd: list[str], **env_extra: str) -> None:
    env = dict(os.environ, **env_extra)
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, env=env)


def klayout_render(gds: Path, out: Path, box: tuple | None, width: int, cell: str = "") -> Image.Image:
    cmd = ["klayout", "-z", "-r", SCRIPTS / "render_layout.py", "-rd", f"gds={gds}", "-rd", f"out={out}", "-rd", f"width={width}"]
    if box:
        cmd += ["-rd", "box=" + ",".join(str(v) for v in box)]
    if cell:
        cmd += ["-rd", f"cell={cell}"]
    run(cmd, QT_QPA_PLATFORM="offscreen")
    return Image.open(out).convert("RGB")


class View:
    """Maps layout µm to pixels of a rendered box."""

    def __init__(self, box, width):
        self.x1, self.y1, self.x2, self.y2 = box
        self.scale = width / (self.x2 - self.x1)

    def px(self, x, y):
        return ((x - self.x1) * self.scale, (self.y2 - y) * self.scale)


def scale_bar(img: Image.Image, view: View, length_um: float) -> None:
    d = ImageDraw.Draw(img)
    f = font(max(14, img.width // 55), bold=True)
    n = length_um * view.scale
    x0, y0 = 18, img.height - 22
    text = f"{length_um:g} µm"
    tw = d.textlength(text, font=f)
    d.rectangle([x0 - 8, y0 - f.size - 14, x0 + max(n, tw) + 8, y0 + 12], fill=BACKGROUND)
    d.rectangle([x0, y0, x0 + n, y0 + 5], fill=WHITE)
    d.text((x0, y0 - f.size - 8), text, font=f, fill=WHITE)


def add_legend(img: Image.Image) -> Image.Image:
    f = font(max(13, img.width // 70))
    pad, sw = 12, f.size
    probe = ImageDraw.Draw(img)
    widths = [sw + 6 + probe.textlength(name, font=f) + 22 for name, _ in LEGEND]
    rows, row, used = [], [], pad
    for item, w in zip(LEGEND, widths):
        if used + w > img.width and row:
            rows.append(row)
            row, used = [], pad
        row.append((item, w))
        used += w
    rows.append(row)
    line_h = f.size + 12
    out = Image.new("RGB", (img.width, img.height + line_h * len(rows) + pad), BACKGROUND)
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    y = img.height + pad // 2 + 4
    for row in rows:
        x = pad
        for (name, colour), w in row:
            if colour is None:
                d.rectangle([x, y, x + sw, y + sw], outline=WHITE, width=2)
            else:
                d.rectangle([x, y, x + sw, y + sw], fill=colour)
            d.text((x + sw + 6, y - 2), name, font=f, fill=WHITE)
            x += w
        y += line_h
    return out


def callout(d: ImageDraw.ImageDraw, view: View, text: str, box, label, f, radius: int) -> None:
    x1, y1 = view.px(box[0], box[3])
    x2, y2 = view.px(box[2], box[1])
    lx, ly = view.px(*label)
    # leader from the label to the nearest point of the box
    nx, ny = min(max(lx, x1), x2), min(max(ly, y1), y2)
    d.line([lx, ly, nx, ny], fill=WHITE, width=3)
    d.rectangle([x1, y1, x2, y2], outline=WHITE, width=3)
    d.ellipse([lx - radius, ly - radius, lx + radius, ly + radius], fill=WHITE, outline=(0, 0, 0), width=2)
    d.text((lx, ly), text, font=f, fill=(0, 0, 0), anchor="mm")


def panel_title(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    f = font(max(15, img.width // 40), bold=True)
    tw = d.textlength(text, font=f)
    d.rectangle([0, 0, tw + 24, f.size + 16], fill=BACKGROUND)
    d.text((12, 7), text, font=f, fill=WHITE)


def side_by_side(images: list[Image.Image], gap: int = 10) -> Image.Image:
    h = max(i.height for i in images)
    w = sum(i.width for i in images) + gap * (len(images) - 1)
    out = Image.new("RGB", (w, h), BACKGROUND)
    x = 0
    for i in images:
        out.paste(i, (x, 0))
        x += i.width + gap
    return out


# ---------------------------------------------------------------------------
# Pad roles
# ---------------------------------------------------------------------------
def classify_pads(data: dict) -> list[dict]:
    """Adds 'launch', 'role', 'row' and 'frame' (frame pad number or None) to each pad."""
    x1, y1, x2, y2 = data["die"]
    nets = data["nets"]
    pads = data["pads"]
    for p in pads:
        net = nets.get(str(p["net"]), {})
        p["ground"] = bool(net.get("substrate_contact"))
        p["launch"] = None
        p["role"] = "NC"
        # distance from the nearest die edge and coordinate along it
        edges = {"bottom": p["y"] - y1, "top": y2 - p["y"], "left": p["x"] - x1, "right": x2 - p["x"]}
        for structure, edge, (a, b), n_sig in LAUNCHES:
            along = p["x"] if edge in ("bottom", "top") else p["y"]
            if a <= along <= b and edges[edge] < 460 and edges[edge] == min(edges.values()):
                p["launch"] = (structure, edge)
                p["depth"] = edges[edge]
                if p["ground"]:
                    p["role"] = "G"
                else:
                    off = along - (a + b) / 2
                    if n_sig == 2:
                        p["role"] = "S1" if off < 0 else "S2"
                    else:
                        p["role"] = "S2" if abs(off) < 20 else ("S1" if off < 0 else "S3")
                break
    # Frame pads are the outermost row, numbered counterclockwise from the lower left.
    outer = 60
    bottom = sorted((p for p in pads if p["y"] - y1 < outer), key=lambda p: p["x"])
    right = sorted((p for p in pads if x2 - p["x"] < outer), key=lambda p: p["y"])
    top = sorted((p for p in pads if y2 - p["y"] < outer), key=lambda p: -p["x"])
    left = sorted((p for p in pads if p["x"] - x1 < outer), key=lambda p: -p["y"])
    for p in pads:
        p["frame"] = None
    for n, p in enumerate(bottom + right + top + left, start=1):
        p["frame"] = n
    return pads


def draw_pad_map(data: dict, out: Path) -> None:
    pads = classify_pads(data)
    x1, y1, x2, y2 = data["die"]
    s = 0.5
    margin = 46
    w, h = int((x2 - x1) * s) + 2 * margin, int((y2 - y1) * s) + 2 * margin
    img = Image.new("RGB", (w, h), BACKGROUND)
    d = ImageDraw.Draw(img)

    def px(x, y):
        return (margin + (x - x1) * s, margin + (y2 - y) * s)

    d.rectangle([*px(x1, y2), *px(x2, y1)], outline=(0x60, 0x68, 0x70), width=2)
    f_small, f_num, f_big = font(11), font(12, bold=True), font(22, bold=True)
    for p in pads:
        a = px(p["x"] - p["w"] / 2, p["y"] + p["h"] / 2)
        b = px(p["x"] + p["w"] / 2, p["y"] - p["h"] / 2)
        colour = ROLE_COLOURS[p["role"]]
        if colour is None:
            d.rectangle([*a, *b], outline=WHITE, width=2)
        else:
            d.rectangle([*a, *b], fill=colour)
            if p["role"] != "G":
                d.text(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), p["role"][1], font=f_num, fill=(0, 0, 0), anchor="mm")
        if p["frame"]:
            cx, cy = px(p["x"], p["y"])
            if p["y"] - y1 < 60:
                pos, anchor = (cx, h - margin + 6), "mt"
            elif y2 - p["y"] < 60:
                pos, anchor = (cx, margin - 6), "mb"
            elif p["x"] - x1 < 60:
                pos, anchor = (margin - 6, cy), "rm"
            else:
                pos, anchor = (w - margin + 6, cy), "lm"
            d.text(pos, str(p["frame"]), font=f_small, fill=WHITE, anchor=anchor)
    for st in STRUCTURES:
        lx, ly = px(*st["label"])
        r = 17
        d.ellipse([lx - r, ly - r, lx + r, ly + r], fill=WHITE)
        d.text((lx, ly), st["id"], font=font(17, bold=True), fill=(0, 0, 0), anchor="mm")
    # key
    key = [("Ground", "G"), ("Signal 1", "S1"), ("Signal 2", "S2"), ("Signal 3", "S3"), ("Not connected", "NC")]
    kx, ky = px(700, 3560)
    d.text((kx, ky - 34), "Pad key", font=f_big, fill=WHITE)
    for name, role in key:
        c = ROLE_COLOURS[role]
        if c is None:
            d.rectangle([kx, ky, kx + 22, ky + 22], outline=WHITE, width=2)
        else:
            d.rectangle([kx, ky, kx + 22, ky + 22], fill=c)
        d.text((kx + 32, ky + 2), name, font=font(16), fill=WHITE)
        ky += 30
    img.save(out, optimize=True)
    print("wrote", out)


def draw_launch(data: dict, structure: str, edge: str, title: str, out: Path) -> None:
    """Dimensioned drawing of one probe launch, die edge at the bottom."""
    pads = [p for p in classify_pads(data) if p["launch"] == (structure, edge)]
    x1, y1, x2, y2 = data["die"]

    def local(p):  # (along the edge, distance from the edge)
        if edge == "left":
            return (y2 - p["y"], p["x"] - x1)
        if edge == "right":
            return (p["y"], x2 - p["x"])
        if edge == "bottom":
            return (p["x"], p["y"] - y1)
        return (x2 - p["x"], y2 - p["y"])

    pts = [(local(p), p) for p in pads]
    a_min = min(a for (a, _), _ in pts)
    a_max = max(a for (a, _), _ in pts)
    d_max = max(dd for (_, dd), _ in pts)
    s = 1.25
    ml, mr, mt, mb = 40, 250, 70, 50
    w = int((a_max - a_min + 60) * s) + ml + mr
    h = int((d_max + 30 + 30) * s) + mt + mb
    img = Image.new("RGB", (w, h), BACKGROUND)
    d = ImageDraw.Draw(img)
    f, fb = font(16), font(18, bold=True)

    def px(a, dd):
        return (ml + (a - a_min + 30) * s, h - mb - dd * s)

    d.text((ml, 16), title, font=font(22, bold=True), fill=WHITE)
    ey = h - mb
    d.line([ml - 20, ey, w - mr + 20, ey], fill=(0x60, 0x68, 0x70), width=3)
    d.text((ml - 20, ey + 10), "die edge", font=f, fill=(0xA0, 0xA8, 0xB0))
    rows: dict[float, list] = {}
    for (a, dd), p in pts:
        cx, cy = px(a, dd)
        half = 30 * s
        d.rectangle([cx - half, cy - half, cx + half, cy + half], fill=ROLE_COLOURS[p["role"]])
        d.text((cx, cy), p["role"], font=fb, fill=(0, 0, 0), anchor="mm")
        rows.setdefault(round(dd), []).append(a)
    for dd, along in sorted(rows.items()):
        along.sort()
        pitch = sorted(set(round(b - a, 1) for a, b in zip(along, along[1:])))
        pitch_text = " and ".join(f"{v:g}" for v in pitch)
        _, cy = px(0, dd)
        d.text((w - mr + 30, cy), f"{len(along)} pads, pitch {pitch_text} µm", font=f, fill=WHITE, anchor="lm")
        d.text((w - mr + 30, cy + 22), f"centre {dd:g} µm from die edge", font=font(13), fill=(0xA0, 0xA8, 0xB0), anchor="lm")
    img.save(out, optimize=True)
    print("wrote", out)


def write_pad_table(data: dict, out: Path) -> None:
    """Writes the Markdown pad tables that docs/README.md carries."""
    pads = classify_pads(data)
    frame = sorted((p for p in pads if p["frame"]), key=lambda p: p["frame"])
    lines = ["| Structure | Die edge | G | S1 | S2 | S3 | G | Pad openings |", "|---|---|---|---|---|---|---|---|"]
    for structure, edge, (a, b), n_sig in LAUNCHES:
        mine = [p for p in pads if p["launch"] == (structure, edge)]
        row = sorted((p for p in mine if p["frame"]), key=lambda p: p["x"] if edge in ("bottom", "top") else p["y"])
        cells = {"S1": "", "S2": "", "S3": ""}
        grounds = []
        for p in row:
            if p["role"] == "G":
                grounds.append(str(p["frame"]))
            else:
                cells[p["role"]] = str(p["frame"])
        if n_sig == 2:
            cells["S3"] = "none"
        lines.append(f"| [^{structure}] | {edge} | {grounds[0]} | {cells['S1']} | {cells['S2']} | {cells['S3']} | {grounds[1]} | {len(mine)} |")
    lines += ["", "| Pad | Centre (µm) | Role | Text label at the pad |", "|---|---|---|---|"]
    for p in frame:
        label = ", ".join(f"`{s}`" for s in p["labels"]) or "none"
        lines.append(f"| {p['frame']} | {p['x']:g},&nbsp;{p['y']:g} | {p['role']} | {label} |")
    lines += ["", f"{len(pads)} pad openings in total, {len(frame)} on the frame row."]
    out.write_text("\n".join(lines) + "\n")
    print("wrote", out)


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", type=Path, default=BUILD, help="scratch directory (default: build/ in the repository root)")
    ap.add_argument("--only", nargs="*", help="only regenerate images whose file name contains one of these words")
    args = ap.parse_args()

    if shutil.which("klayout") is None:
        print("klayout was not found on PATH", file=sys.stderr)
        return 1
    build = args.build
    build.mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)

    gds = build / GDS_NAME
    if not gds.exists() or gds.stat().st_mtime < ZIP.stat().st_mtime:
        with zipfile.ZipFile(ZIP) as z:
            z.extract(GDS_NAME, build)
        os.utime(gds)

    def wanted(name: str) -> bool:
        return not args.only or any(word in name for word in args.only)

    def crop(name: str, box, width: int, bar: float, titles: list[tuple] = (), source: Path = gds, cell: str = "", legend: bool = True):
        if not wanted(name):
            return None
        img = klayout_render(source, build / f"raw_{name}", box, width, cell)
        view = View(box, width)
        d = ImageDraw.Draw(img)
        f = font(max(18, width // 45), bold=True)
        for st_id, pos in titles:
            lx, ly = view.px(*pos)
            r = int(f.size * 0.95)
            d.ellipse([lx - r, ly - r, lx + r, ly + r], fill=WHITE, outline=(0, 0, 0), width=2)
            d.text((lx, ly), st_id, font=f, fill=(0, 0, 0), anchor="mm")
        scale_bar(img, view, bar)
        if legend:
            img = add_legend(img)
        img.save(IMG / name, optimize=True)
        print("wrote", IMG / name)
        return img

    # Whole die with numbered callouts.
    if wanted("die.png"):
        box = (0, 0, 1936, 5122)
        width = 1100
        img = klayout_render(gds, build / "raw_die.png", box, width)
        view = View(box, width)
        d = ImageDraw.Draw(img)
        f = font(26, bold=True)
        for st in STRUCTURES:
            callout(d, view, st["id"], st["box"], st["label"], f, 24)
        scale_bar(img, view, 500)
        add_legend(img).save(IMG / "die.png", optimize=True)
        print("wrote", IMG / "die.png")

    # One picture per structure type.
    crop("mim_capacitors.png", (420, 20, 1516, 500), 1400, 100, [("1", (560, 435)), ("2", (1345, 425))])
    crop("spiral_2turn.png", (1270, 4222, 1640, 4548), 900, 50, [("10", (1300, 4520))])
    crop("spiral_4turn.png", (1270, 3614, 1640, 3940), 900, 50, [("8", (1300, 3912))])
    crop("symmetric_inductor.png", (404, 4146, 774, 4472), 900, 50, [("9", (745, 4444))])
    crop("transformer_1turn.png", (800, 650, 1136, 976), 900, 50, [("3", (968, 813))])
    crop("transformer_2turn.png", (800, 2170, 1136, 2496), 900, 50, [("5", (968, 2333))])
    crop("transformer_row.png", (20, 470, 1916, 1156), 1500, 200, [("3", (968, 1070))])
    crop("thru_3port.png", (20, 1230, 1916, 1916), 1500, 200, [("4", (968, 1830))])
    crop("open_short_3port.png", (20, 2750, 1916, 3436), 1500, 200, [("6", (640, 3093)), ("7", (1296, 3093))])
    crop("open_short_2port.png", (420, 4700, 1516, 5110), 1400, 100, [("11", (692, 4735)), ("12", (1244, 4735))])
    crop("inductor_rows.png", (20, 3500, 1916, 4660), 1500, 200, [("8", (1170, 3777)), ("9", (875, 4309)), ("10", (1170, 4385)), ("13", (230, 3701))])

    # The stand-alone files in seperate_GDSs/.
    for stem, cell in (("Ind2_D250_N2_W26_TO", "SpiralInductor"), ("Ind3_D250_N2_W26_TO", "SymmetricInductor")):
        crop(f"{stem}.png", (-160, -185, 160, 155), 700, 50, source=SEPARATE / f"{stem}.gds", cell=cell)
    for stem in ("bare_frame", "0p5x1p0_frame"):
        crop(f"{stem}.png", (0, 0, 1936, 5122), 500, 500, source=SEPARATE / f"{stem}.gds", cell="chip_top", legend=False)

    # Pad connectivity and the drawings made from it.
    if any(wanted(n) for n in ("pad_map.png", "launch_2port.png", "launch_3port.png")):
        pads_json = build / "pads.json"
        if not pads_json.exists() or pads_json.stat().st_mtime < gds.stat().st_mtime:
            run(["klayout", "-b", "-r", SCRIPTS / "extract_pads.py", "-rd", f"gds={gds}", "-rd", f"out={pads_json}"])
        data = json.loads(pads_json.read_text())
        if wanted("pad_map.png"):
            draw_pad_map(data, IMG / "pad_map.png")
        if wanted("launch_2port.png"):
            draw_launch(data, "2", "bottom", "Two-port launch (G S1 S2 G)", IMG / "launch_2port.png")
        if wanted("launch_3port.png"):
            draw_launch(data, "7", "right", "Three-port launch (G S1 S2 S3 G)", IMG / "launch_3port.png")
        write_pad_table(json.loads(pads_json.read_text()), build / "pad_table.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
