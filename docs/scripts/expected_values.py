#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""First-order expected values for the RLCM test structures.

These are hand-calculation estimates from the drawn geometry and the typical
GF180MCU sheet values. They are a sanity check for measurements and for the
openEMS results, not a replacement for either.

    uv run docs/scripts/expected_values.py

Sources for the constants:

* MIM capacitance per area, 1.8 / 2.0 / 2.2 fF/µm² (min / typ / max):
  https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_6_4.html
* Sheet resistance, Metal1 to Metal5 0.090 Ω/sq and 11 kÅ top metal 0.04 Ω/sq:
  https://gf180mcu-pdk.readthedocs.io/en/latest/analog/layout/inter_specs/inter_specs_4.html
* In the 5-metal gf180mcuD stack the top metal is drawn on Metal5, so Metal5
  takes the top metal value and Metal1 to Metal4 take the thin metal value.
* Inductance: current sheet expression for a square spiral from Mohan,
  del Mar Hershenson, Boyd and Lee, "Simple accurate expressions for planar
  spiral inductances", IEEE JSSC 34(10), 1999, doi:10.1109/4.792620.
"""

import math

MU0 = 4e-7 * math.pi

MIM_FF_PER_UM2 = {"min": 1.8, "typ": 2.0, "max": 2.2}
RS_THIN = 0.090  # Ω/sq, Metal1 to Metal4
RS_TOP = 0.04  # Ω/sq, Metal5 drawn as 11 kÅ top metal

# (name, top plate width µm, top plate length µm), from the FuseTop shapes
MIM_CAPS = [
    ("1  MIM capacitor 100 x 100", 100.0, 100.0),
    ("2  MIM capacitor 54 x 25", 54.0, 25.0),
]

# (name, turns, outer dimension µm, track width µm, spacing µm, Metal5 winding area µm²)
# The Metal5 area is the merged winding polygon reported by KLayout, which
# includes the two terminal stubs.
SPIRALS = [
    ("10 Spiral inductor, two turns", 2, 250.0, 26.0, 2.0, 39598.0),
    ("8  Spiral inductor, four turns", 4, 250.0, 26.0, 2.0, 55613.9),
    ("9  Symmetric inductor, two turns", 2, 250.0, 26.0, 2.0, 29910.4 + 11070.5),
]


def mohan_square(n: int, d_out: float, w: float, s: float) -> tuple[float, float, float]:
    """Returns (inner dimension µm, fill ratio, inductance nH) for a square spiral."""
    d_in = d_out - 2 * (n * w + (n - 1) * s)
    d_avg = (d_out + d_in) / 2
    rho = (d_out - d_in) / (d_out + d_in)
    c1, c2, c3, c4 = 1.27, 2.07, 0.18, 0.13
    henry = MU0 * n**2 * (d_avg * 1e-6) * c1 / 2 * (math.log(c2 / rho) + c3 * rho + c4 * rho**2)
    return d_in, rho, henry * 1e9


def main() -> None:
    print("MIM capacitors (C = area x capacitance per area)")
    for name, w, length in MIM_CAPS:
        area = w * length
        c = {k: area * v / 1000 for k, v in MIM_FF_PER_UM2.items()}
        print(f"  {name}: area {area:.0f} um2, C = {c['typ']:.2f} pF (min {c['min']:.2f}, max {c['max']:.2f})")

    rs_stack = 1 / (4 / RS_THIN + 1 / RS_TOP)
    print()
    print(f"Five stacked metals in parallel: Rs = 1 / (4/{RS_THIN} + 1/{RS_TOP}) = {rs_stack * 1000:.1f} mOhm/sq")
    print()
    print("Inductors (Mohan current sheet expression, square spiral)")
    for name, n, d_out, w, s, area in SPIRALS:
        d_in, rho, nh = mohan_square(n, d_out, w, s)
        squares = area / w**2
        print(f"  {name}: d_in {d_in:.0f} um, fill ratio {rho:.3f}, L = {nh:.2f} nH, about {squares:.0f} squares, R_dc = {squares * rs_stack:.2f} Ohm")


if __name__ == "__main__":
    main()
