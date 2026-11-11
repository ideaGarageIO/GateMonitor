"""
Single source of truth for the Gate Node carrier board.

Both gen_schematic.py and gen_pcb.py read this file, so the schematic and
the PCB are always generated from the same netlist and reference designators.

Edit parts / nets / placement here, then re-run:
    python3 scripts/gen_schematic.py
    python3 scripts/gen_pcb.py        (needs KiCad's pcbnew python module)

Anything marked VERIFY is a mechanical dimension or pin order taken from
memory / typical module listings and must be checked with calipers against
the actual parts before ordering boards.
"""

# --------------------------------------------------------------------------
# Board
# --------------------------------------------------------------------------
BOARD_W = 100.0          # mm
BOARD_H = 70.0           # mm
ORIGIN = (100.0, 100.0)  # top-left corner in KiCad page coordinates

# Heltec WiFi LoRa 32 V3 header geometry, measured from the vector drawing in
# the official datasheet (HTIT-WB32LA_V3.2.pdf, section 4 "Physical dimensions"):
#   board 25.52 x 50.2 mm, 2x18 pins at 2.54 mm, rows centred on the board,
#   row spacing 23.04 mm, pin 1 is 3.36 mm from the USB-C face / 2.70 mm from
#   the PCB edge. Caliper-check on a real board before ordering.
HELTEC_ROW_SPACING = 23.04   # mm between the two 1x18 header rows
HELTEC_USB_FACE_X = 100.6    # x of the USB-C connector face (left board edge = 100)
HELTEC_PIN1_X = HELTEC_USB_FACE_X + 3.36   # pin 1 (GND) is at the USB-C end
HELTEC_TOP_ROW_Y = 110.0     # y of the Heltec "J3" row (3V3 / GPIO1-7)

# --------------------------------------------------------------------------
# GPIO map (gate_node.ino must be updated to match)
# --------------------------------------------------------------------------
GPIO = {
    "LIM_OPEN": 5,
    "LIM_CLOSED": 6,
    "RELAY_OPEN": 7,
    "RELAY_CLOSE": 4,    # was 8 in firmware -- GPIO8 is the SX1262 NSS (LoRa CS)!
    "RELAY_SPARE": 47,
    "BATT_ADC": 2,       # was 1 -- GPIO1 is wired to the Heltec's on-board VBAT divider
    "DHT_DATA": 48,
    "EXP_IO33": 33,
    "EXP_IO34": 34,
}

# Heltec V3 header pin order, pin 1 (GND) at the USB-C end.
# Source: datasheet tables 2.2-1 / 2.2-2 and heltec.org pin map image.
# Heltec "J3" (3V3 / GPIO1-7). Top row when OLED faces up and USB-C points left.
HELTEC_J_GPIO = ["GND", "3V3", "3V3", "37", "46", "45", "42", "41", "40",
                 "39", "38", "1", "2", "3", "4", "5", "6", "7"]
# Heltec "J2" (5V / GPIO19-48). Bottom row.
HELTEC_J_5V = ["GND", "5V", "Ve", "Ve", "44", "43", "RST", "0", "36", "35",
               "34", "33", "47", "48", "26", "21", "20", "19"]


def _heltec_pins(names):
    gpio_to_net = {str(v): k for k, v in GPIO.items()}
    pins = {}
    for i, name in enumerate(names, start=1):
        if name == "GND":
            net = "GND"
        elif name == "3V3":
            net = "+3V3"
        elif name == "5V":
            net = "+5V"
        else:
            net = gpio_to_net.get(name)  # None -> no-connect
        pins[str(i)] = net
    return pins


# --------------------------------------------------------------------------
# Footprint shorthands
# --------------------------------------------------------------------------
FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_CP = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
FP_D41 = "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"
FP_D15 = "Diode_THT:D_DO-15_P10.16mm_Horizontal"
FP_TB2 = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
FP_TB3 = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal"
FP_JST3 = "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"
FP_SOCK18 = "Connector_PinSocket_2.54mm:PinSocket_1x18_P2.54mm_Vertical"
FP_HDR4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
FP_HOLE = "MountingHole:MountingHole_3.2mm_M3"
FP_PTC = "Fuse:Fuse_Bourns_MF-RHT050"
FP_JP3 = "Jumper:SolderJumper-3_P1.3mm_Open_RoundedPad1.0x1.5mm"
FP_MINI360 = "gate_node:Mini360_MP1584"

# --------------------------------------------------------------------------
# Parts
#   ref: (lib_symbol, value, footprint, {pin: net}, group, description)
# Pin numbers are the KiCad symbol / footprint pad numbers.
#   Diodes: 1 = K, 2 = A.  C_Polarized: 1 = +.  SolderJumper_3: 2 = centre.
# --------------------------------------------------------------------------
PARTS = {
    # ---- Heltec module ----------------------------------------------------
    "J1": ("Connector_Generic:Conn_01x18", "Heltec_V3_J3 (3V3/GPIO1-7)", FP_SOCK18,
           _heltec_pins(HELTEC_J_GPIO), "mcu", "Heltec V3 header, 3V3/GPIO side"),
    "J2": ("Connector_Generic:Conn_01x18", "Heltec_V3_J2 (5V/GPIO19-48)", FP_SOCK18,
           _heltec_pins(HELTEC_J_5V), "mcu", "Heltec V3 header, 5V side"),

    # ---- 12 V input & protection -----------------------------------------
    "J6": ("Connector:Screw_Terminal_01x02", "12V BATT", FP_TB2,
           {"1": "BATT_IN", "2": "GND"}, "power", "Battery input"),
    "F1": ("Device:Polyfuse", "MF-RHT050 0.5A", FP_PTC,
           {"1": "BATT_IN", "2": "BATT_F"}, "power", "Resettable fuse"),
    "D1": ("Device:D_Schottky", "1N5819", FP_D41,
           {"1": "VIN", "2": "BATT_F"}, "power", "Reverse-polarity protection"),
    "D2": ("Device:D_TVS", "P6KE18CA", FP_D15,
           {"1": "VIN", "2": "GND"}, "power", "Input surge clamp"),
    "C1": ("Device:C_Polarized", "100uF 35V", FP_CP,
           {"1": "VIN", "2": "GND"}, "power", "Input bulk"),
    "C2": ("Device:C", "100nF", FP_C,
           {"1": "VIN", "2": "GND"}, "power", "Input decoupling"),
    "U1": ("Connector_Generic:Conn_01x04", "Mini360 MP1584 5V", FP_MINI360,
           {"1": "VIN", "2": "GND", "3": "GND", "4": "5V_BUCK"}, "power",
           "Buck module: 1=IN+ 2=IN- 3=OUT- 4=OUT+"),
    "D3": ("Device:D_Schottky", "1N5819", FP_D41,
           {"1": "+5V", "2": "5V_BUCK"}, "power", "Blocks USB back-feed into buck"),
    "C3": ("Device:C_Polarized", "100uF 16V", FP_CP,
           {"1": "+5V", "2": "GND"}, "power", "5V bulk"),

    # ---- Battery sense ----------------------------------------------------
    "R1": ("Device:R", "100k 1%", FP_R,
           {"1": "BATT_F", "2": "BATT_ADC"}, "sense", "Divider top"),
    "R2": ("Device:R", "22k 1%", FP_R,
           {"1": "BATT_ADC", "2": "GND"}, "sense", "Divider bottom (ratio 5.545)"),
    "C4": ("Device:C", "100nF", FP_C,
           {"1": "BATT_ADC", "2": "GND"}, "sense", "ADC filter"),

    # ---- Limit switch inputs (dry contact to GND) -------------------------
    "J7": ("Connector:Screw_Terminal_01x03", "LIMITS", FP_TB3,
           {"1": "LIM_OPEN_EXT", "2": "LIM_CLOSED_EXT", "3": "GND"}, "inputs",
           "Limit switches"),
    "R3": ("Device:R", "10k", FP_R,
           {"1": "+3V3", "2": "LIM_OPEN_EXT"}, "inputs", "Pull-up / wetting"),
    "R4": ("Device:R", "1k", FP_R,
           {"1": "LIM_OPEN_EXT", "2": "LIM_OPEN"}, "inputs", "Series protection"),
    "C5": ("Device:C", "100nF", FP_C,
           {"1": "LIM_OPEN", "2": "GND"}, "inputs", "Debounce (tau=0.1ms)"),
    "D4": ("Device:D_TVS", "P6KE6.8CA", FP_D15,
           {"1": "LIM_OPEN_EXT", "2": "GND"}, "inputs", "Field-wire surge clamp"),
    "R5": ("Device:R", "10k", FP_R,
           {"1": "+3V3", "2": "LIM_CLOSED_EXT"}, "inputs", "Pull-up / wetting"),
    "R6": ("Device:R", "1k", FP_R,
           {"1": "LIM_CLOSED_EXT", "2": "LIM_CLOSED"}, "inputs", "Series protection"),
    "C6": ("Device:C", "100nF", FP_C,
           {"1": "LIM_CLOSED", "2": "GND"}, "inputs", "Debounce"),
    "D5": ("Device:D_TVS", "P6KE6.8CA", FP_D15,
           {"1": "LIM_CLOSED_EXT", "2": "GND"}, "inputs", "Field-wire surge clamp"),

    # ---- Relay modules (off-board, JST-XH cable) --------------------------
    "JP1": ("Jumper:SolderJumper_3_Open", "RELAY_VCC 1-2=3V3 2-3=5V", FP_JP3,
            {"1": "+3V3", "2": "RELAY_VCC", "3": "+5V"}, "relays",
            "Bridge 1-2 for the 3V relay modules in the BOM"),
    "C7": ("Device:C_Polarized", "100uF 16V", FP_CP,
           {"1": "RELAY_VCC", "2": "GND"}, "relays", "Relay coil inrush"),
    "J3": ("Connector_Generic:Conn_01x03", "RELAY OPEN", FP_JST3,
           {"1": "RELAY_VCC", "2": "GND", "3": "RELAY_OPEN"}, "relays",
           "To relay module DC+ / DC- / IN"),
    "J4": ("Connector_Generic:Conn_01x03", "RELAY CLOSE", FP_JST3,
           {"1": "RELAY_VCC", "2": "GND", "3": "RELAY_CLOSE"}, "relays",
           "To relay module DC+ / DC- / IN"),
    "J5": ("Connector_Generic:Conn_01x03", "RELAY SPARE", FP_JST3,
           {"1": "RELAY_VCC", "2": "GND", "3": "RELAY_SPARE"}, "relays",
           "Spare channel (lock, light, ...)"),

    # ---- DHT22 + expansion ------------------------------------------------
    "J8": ("Connector:Screw_Terminal_01x03", "DHT22", FP_TB3,
           {"1": "+3V3", "2": "DHT_DATA", "3": "GND"}, "aux", "DHT22 + / DATA / -"),
    "R7": ("Device:R", "10k", FP_R,
           {"1": "+3V3", "2": "DHT_DATA"}, "aux", "DHT pull-up (DNP if module has one)"),
    "J9": ("Connector_Generic:Conn_01x04", "EXPANSION", FP_HDR4,
           {"1": "+3V3", "2": "EXP_IO33", "3": "EXP_IO34", "4": "GND"}, "aux",
           "Spare GPIO header"),

    # ---- Mechanical -------------------------------------------------------
    "H1": ("Mechanical:MountingHole", "M3", FP_HOLE, {}, "mech", ""),
    "H2": ("Mechanical:MountingHole", "M3", FP_HOLE, {}, "mech", ""),
    "H3": ("Mechanical:MountingHole", "M3", FP_HOLE, {}, "mech", ""),
    "H4": ("Mechanical:MountingHole", "M3", FP_HOLE, {}, "mech", ""),
}

POWER_NETS = {"BATT_IN", "BATT_F", "VIN", "5V_BUCK", "+5V", "+3V3", "RELAY_VCC", "GND"}

# --------------------------------------------------------------------------
# PCB placement: ref -> (x, y, rotation_deg). Absolute KiCad mm.
# --------------------------------------------------------------------------
_x0, _y0 = ORIGIN
PLACEMENT = {
    # Heltec: rotation 90 runs pins 1..18 left to right, pin 1 at the USB-C end
    "J1": (HELTEC_PIN1_X, HELTEC_TOP_ROW_Y, 90),
    "J2": (HELTEC_PIN1_X, HELTEC_TOP_ROW_Y + HELTEC_ROW_SPACING, 90),

    # Field-wiring terminals along the bottom edge, wire entry facing the edge
    "J6": (112.0, 164.0, 0),     # 12V battery
    "J8": (140.0, 164.0, 0),     # DHT22
    "J7": (170.0, 164.0, 0),     # limit switches

    # 12V input chain (left)
    "F1": (104.0, 140.0, 0),
    "D1": (113.0, 140.0, 0),
    "C1": (129.0, 140.0, 0),
    "C2": (136.0, 140.0, 0),
    "U1": (112.0, 150.0, 0),
    "D2": (123.0, 147.0, 0),
    "D3": (123.0, 153.0, 0),
    "C3": (138.0, 152.0, 0),

    # Battery sense + DHT pull-up (centre)
    "R1": (146.0, 140.0, 0),
    "R2": (146.0, 145.0, 0),
    "C4": (146.0, 150.0, 0),
    "R7": (146.0, 155.0, 0),

    # Limit-switch conditioning (bottom right, above J7)
    "R3": (158.0, 138.0, 0),
    "R4": (170.0, 138.0, 0),
    "C5": (182.0, 138.0, 0),
    "R5": (158.0, 143.0, 0),
    "R6": (170.0, 143.0, 0),
    "C6": (182.0, 143.0, 0),
    "D4": (158.0, 149.0, 0),
    "D5": (174.0, 149.0, 0),

    # Relay drive (top right)
    "J9": (160.0, 110.0, 0),
    "JP1": (170.0, 112.0, 0),
    "C7": (170.0, 122.0, 0),
    "J3": (182.0, 108.0, 0),
    "J4": (182.0, 118.0, 0),
    "J5": (182.0, 128.0, 0),

    # Mounting holes
    "H1": (104.0, 104.0, 0),
    "H2": (196.0, 104.0, 0),
    "H3": (104.0, 166.0, 0),
    "H4": (196.0, 166.0, 0),
}

# Silkscreen helper labels: (text, x, y, size_mm)
SILK_TEXT = [
    ("GATE NODE CARRIER rev A", 175.0, 157.0, 1.2),
    ("12V+  GND", 114.5, 158.5, 1.0),
    ("+  DATA  -", 145.0, 158.5, 1.0),
    ("OPEN CLOSED GND", 175.0, 158.5, 1.0),
    ("DC+ DC- IN", 184.5, 103.5, 0.9),
    ("OPEN", 192.5, 108.0, 0.9),
    ("CLOSE", 192.5, 118.0, 0.9),
    ("SPARE", 192.5, 128.0, 0.9),
    ("RLY: 1-2=3V3 2-3=5V", 170.0, 108.5, 0.8),
    ("3V3 IO33 IO34 GND", 160.0, 121.0, 0.8),
    ("HELTEC V3  (OLED UP, USB-C <)", 128.0, 121.4, 1.2),
]

# Heltec module outline for silkscreen (50.2 x 25.5 mm incl. USB-C overhang)
HELTEC_OUTLINE = (HELTEC_USB_FACE_X, HELTEC_TOP_ROW_Y + HELTEC_ROW_SPACING / 2 - 12.75,
                  HELTEC_USB_FACE_X + 50.2, HELTEC_TOP_ROW_Y + HELTEC_ROW_SPACING / 2 + 12.75)
