# KLayout batch script. Renders one region of a GDS file to a PNG.
#
# Run it through update_images.py, or by hand:
#
#   QT_QPA_PLATFORM=offscreen klayout -z -r docs/scripts/render_layout.py \
#       -rd gds=build/RLCMV4_filled.gds -rd out=build/die.png \
#       -rd box=0,0,1936,5122 -rd width=1200
#
# Variables (all passed with -rd name=value):
#   gds     input GDS file
#   out     output PNG file
#   cell    cell to show (default: the largest top cell)
#   box     x1,y1,x2,y2 in µm (default: the cell bounding box)
#   width   image width in pixels (default 1200)
#
# Only the routing metals, the MIM top plate, the pad openings and the EM port
# marker layers are drawn. Each layer is a solid colour and the layers are
# stacked bottom to top, so a lower metal is only visible where nothing covers
# it. The colours are defined in LAYERS below and reused for the legend in
# update_images.py.

import pya

# (GDS layer, datatype, name, fill colour, frame colour, stipple index)
# Stipple 0 is solid, 1 is hollow (outline only).
LAYERS = [
    (34, 0, "Metal1", 0x3A5FCD, 0x3A5FCD, 0),
    (36, 0, "Metal2", 0x2AA198, 0x2AA198, 0),
    (42, 0, "Metal3", 0x5E9E3E, 0x5E9E3E, 0),
    (46, 0, "Metal4", 0xC9722E, 0xC9722E, 0),
    (81, 0, "Metal5", 0xD9C27A, 0xD9C27A, 0),
    (75, 0, "MIM top plate", 0xC04FC0, 0xFFFFFF, 0),
    (37, 0, "Pad opening", 0xFFFFFF, 0xFFFFFF, 1),
    (201, 0, "Port 1", 0xFF3030, 0xFF3030, 0),
    (202, 0, "Port 2", 0xFF3030, 0xFF3030, 0),
    (203, 0, "Port 3", 0xFF3030, 0xFF3030, 0),
    (205, 0, "Port 5", 0xFF3030, 0xFF3030, 0),
    (206, 0, "Port 6", 0xFF3030, 0xFF3030, 0),
    (207, 0, "Port 7", 0xFF3030, 0xFF3030, 0),
]
BACKGROUND = "#10161c"


def var(name, default):
    return globals().get(name, default)


view = pya.LayoutView()
view.load_layout(gds, False)
cv = view.cellview(0)
layout = cv.layout()

cell_name = var("cell", "")
if cell_name:
    cv.cell = layout.cell(cell_name)
else:
    cv.cell = max(layout.top_cells(), key=lambda c: c.bbox().area())

# The dummy fill cells only hold shapes on the *_Dummy datatypes, which are
# not drawn. Hiding the cells just saves time.
for c in layout.each_cell():
    if c.name.endswith("_FILL"):
        view.hide_cell(c.cell_index(), 0)

view.clear_layers()
# KLayout paints later entries of the layer list over earlier ones, so insert
# the layers bottom to top.
for layer, datatype, name, fill_color, frame_color, stipple in LAYERS:
    props = pya.LayerProperties()
    props.source = "%d/%d@1" % (layer, datatype)
    props.name = name
    props.fill_color = fill_color
    props.frame_color = frame_color
    props.dither_pattern = stipple
    props.width = 2 if stipple == 1 else 1
    props.visible = True
    props.transparent = False
    view.insert_layer(view.end_layers(), props)

view.set_config("background-color", BACKGROUND)
view.set_config("grid-visible", "false")
view.set_config("text-visible", "false")
view.set_config("drawing-workers", "4")
view.max_hier()

box_text = var("box", "")
if box_text:
    x1, y1, x2, y2 = [float(v) for v in box_text.split(",")]
    box = pya.DBox(x1, y1, x2, y2)
else:
    box = cv.cell.dbbox()

w = int(var("width", "1200"))
h = int(round(w * box.height() / box.width()))
view.save_image_with_options(out, w, h, 0, 2, 0, box, False)
print("wrote %s %dx%d %s" % (out, w, h, box))
