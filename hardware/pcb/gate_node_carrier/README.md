# Gate Node Carrier Board (rev A)

Interconnect board for the gate node: a Heltec WiFi LoRa 32 V3 plugs into
female headers, and every off-board module and field wire lands on a
connector. 100 x 70 mm, 2 layers, all through-hole, M3 holes in the corners.

KiCad 6 project. **The schematic and PCB are generated** from
`scripts/design.py`. Change parts, nets, or placement there and regenerate:

```bash
cd hardware/pcb/gate_node_carrier/scripts
python3 gen_schematic.py     # -> gate_node_carrier.kicad_sch
python3 gen_pcb.py --check   # placement sanity check only
python3 gen_pcb.py           # -> gate_node_carrier.kicad_pcb (+ net classes in .kicad_pro)
```

`python3 gen_3d.py` regenerates the placeholder 3D models in `gate_node.3dshapes/`.
These are box models of the Heltec V3 (attached to J1) and the Mini360 (U1),
written as VRML for the viewer and STEP for export.

### 3D view / enclosure fit

- Install KiCad's stock models: `sudo apt install kicad-packages3d`
- In the PCB editor: **View → 3D Viewer** (Alt+3)
- STEP for enclosure CAD: **File → Export → STEP** and tick *Substitute similarly
  named models*. From the CLI:
  `KIPRJMOD=$PWD kicad2step --subst-models -o gate_node_carrier.step gate_node_carrier.kicad_pcb`
- Heltec stack height: the female sockets are 8.5 mm, the Heltec PCB top is at
  about 9.5 mm and the OLED top at about 11.9 mm above the carrier. Allow
  about 25 mm of enclosure height above the carrier for JST cables and wiring.

Regenerating the PCB **overwrites routing**. Once you start routing in
KiCad, treat the `.kicad_pcb` as hand-edited and use
*Tools → Update PCB from Schematic* instead. Footprints are already linked
to the schematic symbol UUIDs.

## Block diagram

```
12V battery ─ J6 ─ F1 (0.5A PTC) ─┬─ D1 1N5819 ─ VIN ─┬─ U1 Mini360 ─ D3 ─ +5V ─ Heltec 5V
                                  │                   ├─ D2 P6KE18CA, C1 100µF, C2 100nF
                                  └─ R1 100k / R2 22k ─ BATT_ADC (GPIO2)
Heltec 3V3 ─┬─ JP1 (1-2) ─ RELAY_VCC ─ J3/J4/J5 (JST-XH) ─ relay modules
            ├─ R3/R5 10k pull-ups ─ J7 limit switches (via 1k + 100nF, TVS)
            └─ J8 DHT22 (+ R7 10k pull-up), J9 expansion header
```

## Pin map (firmware must match)

| Net | GPIO | Connector | Change vs current firmware |
|---|---|---|---|
| LIM_OPEN | 5 | J7-1 | — |
| LIM_CLOSED | 6 | J7-2 | — |
| RELAY_OPEN | 7 | J3 | — |
| RELAY_CLOSE | **4** | J4 | was 8; **GPIO8 is the SX1262 LoRa chip-select** |
| RELAY_SPARE | 47 | J5 | new |
| BATT_ADC | **2** | (divider) | was 1; GPIO1 is the Heltec's own VBAT-sense divider. `DIVIDER_RATIO` becomes 5.545 |
| DHT_DATA | 48 | J8-2 | new |
| EXP_IO33 / IO34 | 33 / 34 | J9 | spare |

## BOM changes vs the spreadsheet

The modules from the sheet that this board uses: Heltec V3, relay modules
(now 2 per build plus 1 spare position), Mini360, DHT22. The "0–25V voltage
sensor" module is replaced by R1/R2, which form the same divider with less
standby current. Parts to add:

| Ref | Part | Qty |
|---|---|---|
| J1, J2 | 1x18 2.54 mm female header | 2 |
| J3–J5 | JST-XH B3B-XH-A + 3-pin JST-XH→Dupont cables | 3 |
| J6 | Phoenix MKDS 1,5/2-5.08 (or clone) | 1 |
| J7, J8 | Phoenix MKDS 1,5/3-5.08 | 2 |
| J9 | 1x4 2.54 mm male header | 1 |
| F1 | Bourns MF-RHT050 PTC | 1 |
| D1, D3 | 1N5819 | 2 |
| D2 | P6KE18CA | 1 |
| D4, D5 | P6KE6.8CA | 2 |
| C1 | 100 µF 35 V electrolytic, 6.3 mm | 1 |
| C3, C7 | 100 µF 16 V electrolytic, 6.3 mm | 2 |
| C2, C4–C6 | 100 nF ceramic disc, 5 mm | 4 |
| R1 / R2 | 100k 1% / 22k 1% | 1 / 1 |
| R3, R5, R7 / R4, R6 | 10k / 1k | 3 / 2 |

## VERIFY before ordering boards

These are dimensions or pin orders that came from typical listings or from
memory, not from your parts. Measure them, update `design.py`, and
regenerate.

1. **Heltec geometry**: confirmed from Heltec's datasheet
   ([HTIT-WB32LA_V3.2.pdf](https://resource.heltec.cn/download/WiFi_LoRa_32_V3/HTIT-WB32LA_V3.2.pdf), §2.2 and §4).
   Measured from its vector drawing: rows 23.04 mm apart centre to centre, pitch 2.54 mm,
   pin 1 (GND) at the USB-C end, 3.36 mm from the USB-C face.
   Caliper check: measure across the outside edges of two opposite header pins and subtract
   one pin width (0.64 mm). You should get about 23.0 mm.
2. **Heltec pin order**: confirmed from the datasheet tables and the
   [pin map](https://heltec.org/wp-content/uploads/2023/09/pin.png). Heltec's "J3" is the
   3V3/GPIO1-7 row (board J1, top row with OLED up and USB-C left). Heltec's "J2" is the
   5V/GPIO19-48 row (board J2).
3. **Mini360 pad pitch**: the `gate_node:Mini360_MP1584` pads are 14.6 x 8.6 mm. The pads are
   oversized to tolerate about ±0.5 mm. Also confirm IN+/OUT+ are on the same long edge.
4. **Relay module pin order**: J3–J5 assume DC+ / DC- / IN. Crimp the cable to match your module.
5. **Limit switches must be dry contacts to GND.** If you tap the Apollo 635's own limit inputs,
   check that the Apollo doesn't hold them at 5–12 V first. If it does, the inputs need
   opto-isolation (rev B).
6. Open the schematic and run **ERC**. Open the PCB, run **DRC**, and check the parts in the 3D viewer.

## Notes

- The relay modules in the BOM have 3 V coils, so RELAY_VCC comes from the Heltec 3V3 (JP1 1-2).
  Two relays pulsing together draw about 150 mA from the Heltec's regulator. If you switch to
  5 V relay modules, bridge JP1 2-3 instead.
- D3 stops USB power from back-feeding the buck converter when you debug on the bench with 12 V connected.
- 1k + 100 nF on the limit inputs gives a 0.1 ms RC filter. Firmware debounce still applies.
- Mount the DHT22 outside the enclosure, or in a vented spot, using the J8 terminal.
