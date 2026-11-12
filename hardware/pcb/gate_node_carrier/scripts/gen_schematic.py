#!/usr/bin/env python3
"""Generate gate_node_carrier.kicad_sch (KiCad 6 format) from design.py.

Every symbol pin gets a net label placed exactly on its connection point
(or a no-connect flag), so connectivity is defined purely by design.PARTS.
"""
import datetime
import os
import uuid

import design
from sexpr import Q, dump, find, parse

SYM_DIR = "/usr/share/kicad/symbols"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "gate_node_carrier.kicad_sch")
NS = uuid.UUID("6f1c2d4e-8a7b-4c3d-9e2f-0a1b2c3d4e5f")


def uid(*parts):
    """Deterministic UUIDs so regenerating keeps PCB <-> schematic links."""
    return str(uuid.uuid5(NS, "/".join(parts)))


def symbol_uuid(ref):
    return uid("sym", ref)


# ---------------------------------------------------------------- libraries
_lib_cache = {}


def load_symbol(lib_id):
    lib, name = lib_id.split(":")
    if lib not in _lib_cache:
        with open(os.path.join(SYM_DIR, lib + ".kicad_sym")) as f:
            _lib_cache[lib] = parse(f.read())
    for sym in find(_lib_cache[lib], "symbol"):
        if sym[1] == name:
            sym = [x for x in sym]          # shallow copy
            sym[1] = Q(lib_id)
            return sym
    raise KeyError(lib_id)


def symbol_pins(sym):
    """{pin_number: (x, y, angle)} in library coordinates (Y up)."""
    pins = {}
    base = sym[1].split(":")[1]
    for sub in find(sym, "symbol"):
        unit = int(sub[1][len(base) + 1:].split("_")[0])
        if unit not in (0, 1):
            continue
        for pin in find(sub, "pin"):
            at = find(pin, "at")[0]
            num = find(pin, "number")[0][1]
            pins[str(num)] = (float(at[1]), float(at[2]), int(float(at[3])))
    return pins


# ---------------------------------------------------------------- layout
ROWS = [
    ("mcu", "HELTEC WIFI LORA 32 V3 (module plugs into J1/J2)", None),
    ("power", "12V INPUT, PROTECTION, 5V BUCK", 45.72),
    ("sense", "BATTERY SENSE  (Vbatt = Vadc x 5.545, 17.2V full scale at 3.1V)", 91.44),
    ("inputs", "LIMIT SWITCH INPUTS (dry contact to GND)", 137.16),
    ("relays", "RELAY MODULE CONNECTORS (JST-XH to module DC+/DC-/IN)", 182.88),
    ("aux", "DHT22 + EXPANSION", 228.6),
    ("mech", "MOUNTING", 266.7),
]
ROW_X0 = 132.08
ROW_DX = 30.48


def eff(size=1.27, justify=None, hide=False):
    e = ["effects", ["font", ["size", size, size]]]
    if justify:
        e.append(["justify"] + justify)
    if hide:
        e.append("hide")
    return e


def prop(name, value, idx, x, y, hide=False, justify=None):
    return ["property", Q(name), Q(value), ["id", idx], ["at", fmt(x), fmt(y), 0],
            eff(justify=justify, hide=hide)]


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def main():
    lib_syms = {}
    placements = {}

    for row, title, y in ROWS:
        refs = [r for r, p in design.PARTS.items() if p[4] == row]
        for i, ref in enumerate(refs):
            if row == "mcu":
                placements[ref] = (60.96 if ref == "J1" else 60.96, 76.2 if ref == "J1" else 152.4)
            else:
                placements[ref] = (ROW_X0 + i * ROW_DX, y + 15.24)

    items = []
    texts = []
    for row, title, y in ROWS:
        tx, ty = (25.4, 40.64) if row == "mcu" else (ROW_X0 - 12.7, y + 3.81)
        texts.append(["text", Q(title), ["at", fmt(tx), fmt(ty), 0],
                      eff(1.778, ["left", "bottom"]), ["uuid", uid("text", row)]])

    instances = []
    for ref, (lib_id, value, footprint, netmap, group, desc) in design.PARTS.items():
        if lib_id not in lib_syms:
            lib_syms[lib_id] = load_symbol(lib_id)
        sym = lib_syms[lib_id]
        pins = symbol_pins(sym)
        sx, sy = placements[ref]
        su = symbol_uuid(ref)

        ys = [sy - p[1] for p in pins.values()] or [sy]
        xs = [sx + p[0] for p in pins.values()] or [sx]
        vertical_2pin = len(pins) == 2 and all(p[2] in (90, 270) for p in pins.values())
        if vertical_2pin:
            ref_at, val_at, just = (sx + 2.54, sy - 1.27), (sx + 2.54, sy + 1.27), ["left"]
        elif lib_id.startswith(("Connector", "Mechanical")) or ref.startswith("U"):
            ref_at, val_at, just = (sx, min(ys) - 3.81), (sx, max(ys) + 3.81), None
        else:
            ref_at, val_at, just = (sx, sy - 3.81), (sx, sy + 3.81), None

        in_bom = "no" if group == "mech" else "yes"
        node = ["symbol", ["lib_id", Q(lib_id)], ["at", fmt(sx), fmt(sy), 0], ["unit", 1],
                ["in_bom", in_bom], ["on_board", "yes"], ["uuid", su],
                prop("Reference", ref, 0, *ref_at, justify=just),
                prop("Value", value, 1, *val_at, justify=just),
                prop("Footprint", footprint, 2, sx, sy, hide=True),
                prop("Datasheet", "", 3, sx, sy, hide=True)]
        if desc:
            node.append(prop("Notes", desc, 4, sx, sy, hide=True))
        for num in pins:
            node.append(["pin", Q(num), ["uuid", uid("pin", ref, num)]])
        items.append(node)
        instances.append(["path", Q("/" + su), ["reference", Q(ref)], ["unit", 1],
                          ["value", Q(value)], ["footprint", Q(footprint)]])

        for num, (px, py, ang) in pins.items():
            x, y = sx + px, sy - py            # library Y is up, sheet Y is down
            net = netmap.get(num)
            if net is None:
                items.append(["no_connect", ["at", fmt(x), fmt(y)], ["uuid", uid("nc", ref, num)]])
                continue
            la = (ang + 180) % 360
            justify = ["left", "bottom"] if la in (0, 90) else ["right", "bottom"]
            items.append(["label", Q(net), ["at", fmt(x), fmt(y), la],
                          eff(justify=justify), ["uuid", uid("label", ref, num)]])

    sch = ["kicad_sch", ["version", 20211123], ["generator", "eeschema"],
           ["uuid", uid("sheet")], ["paper", Q("A3")],
           ["title_block", ["title", Q("Gate Node Carrier")],
            ["date", Q(datetime.date.today().isoformat())], ["rev", Q("A")],
            ["comment", 1, Q("Generated by scripts/gen_schematic.py from scripts/design.py")],
            ["comment", 2, Q("Edit design.py and regenerate; manual edits are overwritten")]],
           ["lib_symbols"] + list(lib_syms.values())]
    sch += texts + items
    sch.append(["sheet_instances", ["path", Q("/"), ["page", Q("1")]]])
    sch.append(["symbol_instances"] + instances)

    with open(OUT, "w") as f:
        f.write(dump(sch) + "\n")
    nets = sorted({n for p in design.PARTS.values() for n in p[3].values() if n})
    print(f"wrote {os.path.relpath(OUT)}: {len(design.PARTS)} symbols, {len(nets)} nets")


if __name__ == "__main__":
    main()
