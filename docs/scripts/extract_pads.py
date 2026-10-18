# KLayout batch script. Finds every pad opening in a GDS file and the net it
# belongs to, and writes the result as JSON.
#
# Run it through update_images.py, or by hand:
#
#   klayout -b -r docs/scripts/extract_pads.py \
#       -rd gds=build/RLCMV4_filled.gds -rd out=build/pads.json
#
# Variables (all passed with -rd name=value):
#   gds   input GDS file
#   out   output JSON file
#   cell  top cell (default: the largest top cell)
#
# Nets are traced through COMP, Contact, Metal1 to Metal5 and Via1 to Via4.
# A Via4 that lands on the MIM top plate (FuseTop) connects Metal5 to the plate
# and not to Metal4, so the two plates of a MIM capacitor stay separate nets.
# The dummy fill and seal ring cells are removed first.
#
# An inductor winding is a DC short, so both ends of a winding are reported as
# the same net.

import json

import pya

layout = pya.Layout()
layout.read(gds)
cell_name = globals().get("cell", "")
if cell_name:
    top = layout.cell(cell_name)
else:
    top = max(layout.top_cells(), key=lambda c: c.bbox().area())

for c in list(layout.each_cell()):
    if c.name.endswith("_FILL") or c.name.startswith("sealring"):
        layout.prune_cell(c.cell_index(), -1)

GDS_LAYERS = {
    "comp": (22, 0),
    "contact": (33, 0),
    "metal1": (34, 0),
    "via1": (35, 0),
    "metal2": (36, 0),
    "via2": (38, 0),
    "metal3": (42, 0),
    "via3": (40, 0),
    "metal4": (46, 0),
    "via4": (41, 0),
    "metal5": (81, 0),
    "mim": (75, 0),
}

l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(layout, top, []))
region = {}
for name, (layer, datatype) in GDS_LAYERS.items():
    region[name] = l2n.make_layer(layout.layer(layer, datatype), name)

via4_on_mim = region["via4"] & region["mim"]
via4_plain = region["via4"] - region["mim"]
l2n.register(via4_on_mim, "via4_on_mim")
l2n.register(via4_plain, "via4_plain")

for name in ("comp", "metal1", "metal2", "metal3", "metal4", "metal5", "mim"):
    l2n.connect(region[name])
STACK = [
    ("comp", "contact", "metal1"),
    ("metal1", "via1", "metal2"),
    ("metal2", "via2", "metal3"),
    ("metal3", "via3", "metal4"),
]
for lower, via, upper in STACK:
    l2n.connect(region[lower], region[via])
    l2n.connect(region[via], region[upper])
l2n.connect(region["metal4"], via4_plain)
l2n.connect(via4_plain, region["metal5"])
l2n.connect(region["metal5"], via4_on_mim)
l2n.connect(via4_on_mim, region["mim"])
l2n.extract_netlist()

dbu = layout.dbu

# Text labels on Metal5_Label (81/10) placed directly in the top cell. In this
# layout they are the pad names left over from the wafer.space frame template.
labels = []
for shape in top.shapes(layout.layer(81, 10)).each():
    if shape.is_text():
        t = shape.text
        labels.append((t.x * dbu, t.y * dbu, t.string))

pad_region = pya.Region(pya.RecursiveShapeIterator(layout, top, layout.layer(37, 0)))
pad_region.merge()

pads = []
nets = {}
for poly in pad_region.each():
    box = poly.bbox()
    centre = box.center()
    net = l2n.probe_net(region["metal5"], pya.Point(centre.x, centre.y))
    net_id = None
    if net is not None:
        net_id = net.cluster_id
        if net_id not in nets:
            m5 = l2n.shapes_of_net(net, region["metal5"], True).bbox()
            nets[net_id] = {
                "substrate_contact": not l2n.shapes_of_net(net, region["comp"], True).is_empty(),
                "mim_top_plate": not l2n.shapes_of_net(net, region["mim"], True).is_empty(),
                "metal5_bbox": [m5.left * dbu, m5.bottom * dbu, m5.right * dbu, m5.top * dbu],
            }
    x1, y1, x2, y2 = box.left * dbu, box.bottom * dbu, box.right * dbu, box.top * dbu
    names = sorted(s for (x, y, s) in labels if "_PAD" in s and x1 <= x <= x2 and y1 <= y <= y2)
    pads.append({"x": centre.x * dbu, "y": centre.y * dbu, "w": x2 - x1, "h": y2 - y1, "net": net_id, "labels": names})

pads.sort(key=lambda p: (p["y"], p["x"]))
bbox = top.dbbox()
result = {
    "cell": top.name,
    "die": [bbox.left, bbox.bottom, bbox.right, bbox.top],
    "pads": pads,
    "nets": nets,
}
with open(out, "w") as f:
    json.dump(result, f, indent=1)
print("%d pad openings on %d nets written to %s" % (len(pads), len(nets), out))
