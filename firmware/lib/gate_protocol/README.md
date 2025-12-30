# Gate Protocol Library

Shared protocol definitions for LoRa communication between gate node and house gateway.

## Usage

Copy `gate_protocol.h` to your Arduino sketch folder, or install as a library.

### Arduino IDE Library Installation

1. Create folder: `~/Arduino/libraries/gate_protocol/`
2. Copy `gate_protocol.h` to that folder
3. Include in sketches: `#include <gate_protocol.h>`

### Direct Include

Copy `gate_protocol.h` to your sketch folder and include:
```cpp
#include "gate_protocol.h"
```

## Message Format

All messages use pipe-delimited ASCII format for easy debugging and parsing.

| Type | Format | Example |
|------|--------|---------|
| STATUS | `S\|<state>\|<battery_mv>\|<seq>` | `S\|1\|12600\|42` |
| HEARTBEAT | `H\|<state>\|<battery_mv>\|<seq>` | `H\|1\|12500\|43` |
| COMMAND | `C\|<cmd>\|<seq>` | `C\|1\|100` |
| ACK | `A\|<seq>` | `A\|42` |

## State Values

| Value | State |
|-------|-------|
| 0 | UNKNOWN |
| 1 | CLOSED |
| 2 | OPEN |
| 3 | MOVING |
| 4 | ERROR |

## Command Values

| Value | Command |
|-------|---------|
| 1 | OPEN |
| 2 | CLOSE |
| 3 | STOP |
| 4 | STATUS (request) |
