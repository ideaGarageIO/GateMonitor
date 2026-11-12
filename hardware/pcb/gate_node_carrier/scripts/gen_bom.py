#!/usr/bin/env python3
"""Generate bom_amazon.csv: the carrier board's discrete parts, grouped into
Amazon purchase lines.

Columns match the project's Google Sheet BOM so rows can be pasted in. Links
are Amazon *search* URLs for the exact spec. Pick a listing, then paste its
product URL and price into the sheet.
"""
import csv
import os
from collections import defaultdict
from urllib.parse import quote_plus

import design

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "bom_amazon.csv"))

# Parts bought as modules (already in the sheet) or not purchased at all
NOT_DISCRETE = {"H1", "H2", "H3", "H4", "U1"}

# line key -> (component, spec description, amazon search terms, typical pack)
LINES = {
    "sock": ("Female pin header 2.54mm",
             "1x40 straight female header strip; cut into 2x 1x18 for the Heltec (cutting loses 1 pin)",
             "2.54mm female pin header 1x40 single row", "10-20 strips"),
    "hdr": ("Male pin header 2.54mm",
            "1x40 breakaway male header; 1x4 for J9 plus 4 single pins to stand the Mini360 off the board",
            "2.54mm male pin header breakaway 1x40", "10-40 strips"),
    "jst": ("JST-XH 3-pin connector + cable",
            "JST-XH 2.5mm 3-pin: B3B-XH-A vertical PCB header + pre-crimped 3-pin cable, Dupont female on the far end for the relay modules",
            "JST XH 2.5mm 3 pin pcb header pre-crimped cable dupont", "10-20 sets"),
    "tb2": ("Screw terminal 5.08mm 2-pos",
            "PCB screw terminal, 5.08mm pitch, 2 position (KF301-2P / MKDS style)",
            "KF301 5.08mm pcb screw terminal 2 pin 3 pin", "assortment"),
    "tb3": ("Screw terminal 5.08mm 3-pos",
            "PCB screw terminal, 5.08mm pitch, 3 position (KF301-3P / MKDS style)",
            "KF301 5.08mm pcb screw terminal 2 pin 3 pin", "assortment"),
    "ptc": ("PTC resettable fuse 0.5A",
            "Radial PPTC, 0.5A hold / 1A trip, >=30V (RXEF050, MF-R050 or equivalent), 5mm lead pitch",
            "PPTC resettable fuse 0.5A 60V radial", "10-50"),
    "1n5819": ("Schottky diode 1N5819",
               "1N5819, 40V 1A, DO-41 axial",
               "1N5819 schottky diode DO-41", "20-100"),
    "tvs18": ("TVS diode P6KE18CA",
              "P6KE18CA, 600W bidirectional, 15.3V standoff, DO-15 axial",
              "P6KE18CA TVS diode", "10-50"),
    "tvs68": ("TVS diode P6KE6.8CA",
              "P6KE6.8CA (P6KE6V8CA), 600W bidirectional, 5.8V standoff, DO-15 axial",
              "P6KE6.8CA TVS diode bidirectional", "10-50"),
    "cp100": ("Electrolytic cap 100uF 35V",
              "100uF 35V radial, 6.3mm diameter, 2.5mm lead pitch, 105C (35V covers the 16V positions too)",
              "100uF 35V electrolytic capacitor 6.3x11mm radial", "20-100"),
    "c100n": ("Ceramic cap 100nF",
              "100nF (104) 50V ceramic, radial, 5.08mm lead pitch",
              "104 100nF 50V ceramic capacitor 5.08mm", "50-100"),
    "res": ("Resistor kit 1% metal film 1/4W",
            "1/4W 1% metal film, 6.3mm body. Needs 1k, 10k, 22k, 100k; one kit covers every build",
            "1/4W 1% metal film resistor kit assortment", "kit"),
}


def line_for(ref, value, fp):
    v = value.lower()
    if ref in ("J1", "J2"):
        return "sock"
    if ref == "J9":
        return "hdr"
    if "JST" in fp:
        return "jst"
    if "MKDS-1,5-2" in fp:
        return "tb2"
    if "MKDS-1,5-3" in fp:
        return "tb3"
    if ref.startswith("F"):
        return "ptc"
    if "1n5819" in v:
        return "1n5819"
    if "p6ke18" in v:
        return "tvs18"
    if "p6ke6.8" in v:
        return "tvs68"
    if fp.endswith("CP_Radial_D6.3mm_P2.50mm"):
        return "cp100"
    if v.startswith("100nf"):
        return "c100n"
    if ref.startswith("R"):
        return "res"
    if ref.startswith("JP"):
        return None   # solder jumper: copper only
    raise SystemExit(f"no purchasing line for {ref} ({value}, {fp}); add one to LINES")


def main():
    groups = defaultdict(list)
    values = defaultdict(set)
    for ref, (_, value, fp, _, _, _) in design.PARTS.items():
        if ref in NOT_DISCRETE:
            continue
        key = line_for(ref, value, fp)
        if key:
            groups[key].append(ref)
            values[key].add(value.split(" (")[0])

    # Physical quantity per build where a line is not one-part-per-ref
    qty_override = {"sock": 1, "hdr": 1, "res": 1}

    header = ["Component", "Description", "Link", "Required SKU", "Units per SKU",
              "SKU Price", "Price Per Unit", "Required Units", "Price Per Build",
              "Total Price", "Board Refs", "Typical Pack"]
    rows = []
    for key, (comp, desc, search, pack) in LINES.items():
        refs = sorted(groups.get(key, []), key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):])))
        if not refs:
            continue
        if key == "res":
            counts = defaultdict(int)
            for r in refs:
                counts[design.PARTS[r][1].split()[0]] += 1
            desc += " (" + ", ".join(f"{n}x {v}" for v, n in sorted(counts.items())) + ")"
        url = "https://www.amazon.com/s?k=" + quote_plus(search)
        rows.append([comp, desc, url, 1, "", "", "", qty_override.get(key, len(refs)),
                     "", "", " ".join(refs), pack])

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {os.path.relpath(OUT)}: {len(rows)} purchase lines covering "
          f"{sum(len(v) for v in groups.values())} board parts")


if __name__ == "__main__":
    main()
