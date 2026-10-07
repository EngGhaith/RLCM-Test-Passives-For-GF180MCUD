# Updating the pictures

Every picture in [`docs/img/`](img) is generated from the layout files in this
repository by the scripts in [`docs/scripts/`](scripts). Regenerate them
whenever a layout file changes.

## Requirements

| Tool | Used for | Tested with |
|---|---|---|
| [KLayout](https://www.klayout.de/) on `PATH` as `klayout` | rendering the GDS files and tracing the pad connectivity | 0.30.0 |
| [uv](https://docs.astral.sh/uv/) | running the Python scripts with their dependencies | |
| DejaVu Sans fonts | labels on the pictures. Without them the labels fall back to a small built-in font | |

Pillow is the only Python dependency. It is declared inside
[`update_images.py`](scripts/update_images.py), and `uv` installs it on the
first run.

## Regenerating everything

From anywhere inside a clone:

```sh
uv run docs/scripts/update_images.py
```

This takes a few minutes. Most of the time goes into loading the 190 MB chip
layout once per picture and into the connectivity trace. The script:

1. Unzips [`RLCMV4_filled.zip`](../RLCMV4_filled.zip) into `build/` at the
   repository root. `build/` is listed in [`.gitignore`](../.gitignore).
2. Renders each view with KLayout and writes the raw render to `build/`.
3. Adds the numbered callouts, the scale bar and the colour legend, and writes
   the result to [`docs/img/`](img).
4. Traces the pad connectivity into `build/pads.json` and draws the pad map and
   the two launch diagrams from it.
5. Writes `build/pad_table.md`, the two pad tables that
   [`docs/README.md`](README.md#pads) carries. Copy them over by hand if they
   changed.

To regenerate only some pictures, name them. A picture is selected when its
file name contains one of the words:

```sh
uv run docs/scripts/update_images.py --only die.png transformer
```

Check the result with `git status` and look at every changed picture before
committing.

## The scripts

| Script | Run by | What it does |
|---|---|---|
| [`update_images.py`](scripts/update_images.py) | you, with `uv run` | Runs the other two, then annotates and saves the pictures |
| [`render_layout.py`](scripts/render_layout.py) | KLayout, `klayout -z -r` | Renders one region of one GDS file to a PNG |
| [`extract_pads.py`](scripts/extract_pads.py) | KLayout, `klayout -b -r` | Lists every pad opening with the net it belongs to, as JSON |
| [`expected_values.py`](scripts/expected_values.py) | you, with `uv run` | Prints the hand-calculated capacitance, inductance and resistance. It draws nothing |
| [`check_docs.py`](scripts/check_docs.py) | you, with `uv run` | Checks the Markdown files. See [Checking the documents](#checking-the-documents) |

Both KLayout scripts can be run on their own. The command line is in the
comment at the top of each.

## The pictures

| Picture | Source layout | Region (µm) |
|---|---|---|
| [`die.png`](img/die.png) | chip | whole die |
| [`pad_map.png`](img/pad_map.png) | chip, pad trace | whole die |
| [`launch_2port.png`](img/launch_2port.png) | chip, pad trace | bottom launch of structure 2 |
| [`launch_3port.png`](img/launch_3port.png) | chip, pad trace | launch of structure 7 |
| [`mim_capacitors.png`](img/mim_capacitors.png) | chip | 420,&nbsp;20 to 1516,&nbsp;500 |
| [`spiral_2turn.png`](img/spiral_2turn.png) | chip | 1270,&nbsp;4222 to 1640,&nbsp;4548 |
| [`spiral_4turn.png`](img/spiral_4turn.png) | chip | 1270,&nbsp;3614 to 1640,&nbsp;3940 |
| [`inductor_rows.png`](img/inductor_rows.png) | chip | 20,&nbsp;3500 to 1916,&nbsp;4660 |
| [`symmetric_inductor.png`](img/symmetric_inductor.png) | chip | 404,&nbsp;4146 to 774,&nbsp;4472 |
| [`transformer_1turn.png`](img/transformer_1turn.png) | chip | 800,&nbsp;650 to 1136,&nbsp;976 |
| [`transformer_2turn.png`](img/transformer_2turn.png) | chip | 800,&nbsp;2170 to 1136,&nbsp;2496 |
| [`transformer_row.png`](img/transformer_row.png) | chip | 20,&nbsp;470 to 1916,&nbsp;1156 |
| [`thru_3port.png`](img/thru_3port.png) | chip | 20,&nbsp;1230 to 1916,&nbsp;1916 |
| [`open_short_3port.png`](img/open_short_3port.png) | chip | 20,&nbsp;2750 to 1916,&nbsp;3436 |
| [`open_short_2port.png`](img/open_short_2port.png) | chip | 420,&nbsp;4700 to 1516,&nbsp;5110 |
| [`Ind2_D250_N2_W26_TO.png`](img/Ind2_D250_N2_W26_TO.png) | [`Ind2_D250_N2_W26_TO.gds`](../seperate_GDSs/Ind2_D250_N2_W26_TO.gds) | whole cell |
| [`Ind3_D250_N2_W26_TO.png`](img/Ind3_D250_N2_W26_TO.png) | [`Ind3_D250_N2_W26_TO.gds`](../seperate_GDSs/Ind3_D250_N2_W26_TO.gds) | whole cell |
| [`bare_frame.png`](img/bare_frame.png) | [`bare_frame.gds`](../seperate_GDSs/bare_frame.gds) | whole die |
| [`0p5x1p0_frame.png`](img/0p5x1p0_frame.png) | [`0p5x1p0_frame.gds`](../seperate_GDSs/0p5x1p0_frame.gds) | whole die |

"chip" is the GDS file inside [`RLCMV4_filled.zip`](../RLCMV4_filled.zip).

## How the layout is drawn

The renders do not use the PDK's layer properties file. With five metals
stacked on top of each other, the standard hatch patterns turn the inductors
into an unreadable moiré. Instead
[`render_layout.py`](scripts/render_layout.py) draws a short list of layers as
solid colours, bottom to top:

| Layer | GDS layer | Colour |
|---|---|---|
| Metal1 | 34/0 | blue |
| Metal2 | 36/0 | teal |
| Metal3 | 42/0 | green |
| Metal4 | 46/0 | orange |
| Metal5 | 81/0 | sand |
| MIM top plate | 75/0 | magenta |
| Pad opening | 37/0 | white outline |
| EM port markers | 201/0 to 207/0 | red |

A lower metal is visible only where no higher metal covers it. That is what
makes the Metal1 and Metal2 underpasses and crossovers stand out. Vias, slots,
the substrate layers and the dummy fill are not drawn.

The legend under each picture is built from the `LEGEND` list in
[`update_images.py`](scripts/update_images.py). If you change a colour in
[`render_layout.py`](scripts/render_layout.py), change it there too.

## Changing what is shown

All positions are in µm in the top cell of the chip layout and live in
[`update_images.py`](scripts/update_images.py):

| To change | Edit |
|---|---|
| The numbered boxes on the whole-die picture | `STRUCTURES`: `box` is the outline, `label` is where the number sits |
| Which pads belong to which structure | `LAUNCHES`: the die edge and the range along it |
| The region of a close-up, its width in pixels, its scale bar and its number | the matching `crop(...)` line in `main()` |

If the chip layout itself changes, check the pad map first. Pads that show up
as "not connected", or a launch with the wrong number of signal pads, mean
that `LAUNCHES` no longer matches the layout.

## How the pad roles are found

[`extract_pads.py`](scripts/extract_pads.py) traces nets through COMP,
Contact, Metal1 to Metal5 and Via1 to Via4 with KLayout's `LayoutToNetlist`.
Three things are worth knowing when you read its output:

| Behaviour | Consequence |
|---|---|
| A net with a substrate contact is treated as ground | every other pad in a launch is a signal pad |
| A Via4 on the MIM top plate connects Metal5 to the plate and not to Metal4 | the two plates of a capacitor stay separate nets |
| A winding is a DC short | both ends of an inductor, and its centre tap, come out as one net. S1, S2 and S3 are told apart by position, not by net |

The seal ring and the dummy fill are removed before tracing, to keep the run
time down.

## Checking the documents

After any edit, check the links, image paths, anchors, footnotes, heading
levels and punctuation of every Markdown file:

```sh
uv run docs/scripts/check_docs.py
```
