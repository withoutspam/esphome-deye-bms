# Modular InterCAN package

This package receives the four extended voltage frames used by the upstream
RW-M6.1 / SE-G5.1Pro decoder. Each frame contains four unsigned big-endian
millivolt readings. It handles one 16-cell module per package instance.
**SE-F16 compatibility has not been verified on hardware.** Do not interpret a
successful build as proof of the port pinout, bitrate or protocol compatibility.

## Include it in an existing device

Keep the device's ESP-IDF, UART, Modbus, Wi-Fi, API, OTA and other packages.
Add a CAN controller only if the device does not already define the desired one:

```yaml
canbus:
  - platform: esp32_can
    id: intercan_bus
    tx_pin: GPIO15
    rx_pin: GPIO16
    can_id: 0
    bit_rate: 250kbps
    mode: NORMAL
```

GPIO15/16 are the native CAN pins on the Waveshare ESP32-S3-RS485-CAN.
Its RS485 uses GPIO17/18/21; CAN does not require a second UART or MCP2515.
The 250 kbps setting comes from upstream InterCAN, not PCS (500 kbps).
Verify the hardware revision, OUT pinout, bitrate and termination first.
The controller's `can_id` is required by ESPHome; it is not the selected battery
address, and this package does not transmit application frames.

Add the following entry to the device's **existing** `packages:` mapping:

```yaml
packages:
  # Keep all your existing entries here.
  battery: !include
    file: packages/deye-intercan.yaml
    vars:
      bms_id: battery
      bms_name: Battery
      bms_canbus_id: intercan_bus
      bms_module_address: "1"
      bms_update_interval: 5s
      bms_timeout_ms: "30000"
      bms_max_group_skew_ms: "2000"
```

Copy the package into your local `packages/` directory for this example.
For a Git package, ESPHome also accepts a `url`, a reviewed commit SHA in `ref`,
and a `files` entry with `path: packages/deye-intercan.yaml` and the same `vars`.
Pin a reviewed commit for installed devices; avoid following a moving branch.
Choose a unique `bms_id` and `bms_name` for each instance. The ID is a valid
ESPHome identifier, such as `battery_2`, and is a prefix for internal IDs.

## Parameters

| Variable | Default | Meaning |
| --- | --- | --- |
| `bms_id` | `battery` | Unique internal ID prefix |
| `bms_name` | `Battery` | Entity name prefix |
| `bms_canbus_id` | `intercan_bus` | Existing controller to extend |
| `bms_module_address` | `1` | Low byte of the extended IDs, 1–255; not auto-discovered |
| `bms_update_interval` | `5s` | Publication period; it does not poll the BMS |
| `bms_timeout_ms` | `30000` | A group expires at this age, 1–2147483647 ms |
| `bms_max_group_skew_ms` | `2000` | Maximum age difference between four groups, 1–timeout |
| `bms_min_cell_mv` | `1500` | Inclusive lower sanity bound |
| `bms_max_cell_mv` | `4500` | Inclusive upper sanity bound |

Timeouts and sanity bounds are decoder checks, **not charging or protection
settings**. Measure the actual frame cycle before choosing timeouts. Expiry is
published on the next publication tick, so allow up to one additional publication
period before Home Assistant receives it. An interval longer than the timeout
can miss valid readings. Invalid numeric bounds fail C++ compilation with a
specific diagnostic; YAML validation alone does not evaluate those assertions.

## Data and diagnostics

For module address 1, voltage IDs are `0x04008001`, `0x04018001`, `0x04028001`
and `0x04038001`. The address substitutes the low byte. Standard frames, RTR
frames, other addresses and other IDs are ignored. The ESPHome callback must deliver
eight bytes, with all four values within the configured bounds. A bad
payload is rejected atomically and does not refresh any timestamp. ESPHome
normalizes raw DLC values above eight to an eight-byte callback payload; a YAML
`on_frame` handler cannot distinguish them from raw DLC 8. This package checks
the delivered payload length and does not claim to reject such raw DLC values.

The package exposes 16 cell voltages; derived minimum/maximum, their 1-based
indices, voltage sum and delta in mV; fresh cell count, age of the last accepted
voltage frame, valid/rejected frame counts and a `Data Complete` binary sensor.
Equal extrema use the first cell index. Counters are diagnostic and restart
from zero with the device. All sensors are published in one script execution.

Each group has its own age. A fresh group remains visible when another group
expires; expired cells become NaN (unavailable in HA). Aggregates require all
16 readings to be fresh and within the skew window. They become unavailable
otherwise. `Data Complete` is not proof of an atomic BMS sampling cycle: it means
all four groups were received within the configured time window. Repeated
publication never refreshes the original reception timestamps. Expired groups
are invalidated until a new accepted frame arrives, including across a full
32-bit clock cycle. The age sensor is unavailable when all groups have expired. Values and
received flags are not restored across reboots.

This first package derives extrema from the 16 readings; it does not decode the
separate BMS-reported extrema frame, temperatures, SOC, current or balancing bits.
Keep existing inverter measurements for those until their source is verified.

## ACK, diagnostic requests and installation

`NORMAL` participates in CAN acknowledgments and error signaling. It is the
starting point for a segment containing only battery + ESP. `LISTENONLY` sends
neither data nor ACK, and is suitable for monitoring a bus with another active
receiver. The decoder itself contains no `canbus.send`, automatic wake-up,
charge control, PCS emulation or external telemetry.

The original example sends extended `0x18A2FF80` with payload `01` on InterCAN
when it receives PCS `0x351`. That diagnostic initialization is deliberately not
included here: OUT-only wiring does not supply that PCS trigger, and the request
must be verified for the specific BMS. Missing voltage frames can mean wrong
bitrate/address/wiring or an inactive diagnostic stream; normal ACK alone does
not enable the stream. Do not send commands copied from another model blindly.

Preserve the battery's original PCS/inverter connection. Confirm the actual
termination at both ends of a separate two-node segment rather than adding a
third terminator from another example. Compare each cell against the BMS app,
then the sum against pack voltage, allowing for different measurement times.
Observe existing Modbus/API, memory, loop time and restarts after installation.
Keep a known-good firmware/configuration backup before changing a working device.

## Checks

The native suite compiles the **actual YAML lambda bodies** as C++17 and executes
them with hand-checked CAN frames and a simulated clock. Only the publication
boundary is replaced; there is no second decoder in the tests. Configuration
tests invoke real ESPHome 2026.10.1, including an existing Modbus client and two
independently named BMS instances sharing one CAN controller. They also run
ESPHome firmware C++ generation. This is not a full ESP32 cross-compilation.

```sh
python3 -m pip install -r tests/requirements-validation.txt
python3 -m unittest discover -s tests -v
```

A C++17 compiler (`g++` or `clang++`) is required. Alternatively, build the test
image, then run with the repository read-only and networking disabled:

```sh
docker build -f tests/Dockerfile -t deye-intercan-checks .
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 32 --cpus 2 --memory 512m \
  --tmpfs /tmp:rw,exec,nosuid,size=192m --user 65534:65534 \
  --mount type=bind,src="$PWD",dst=/src,readonly --workdir /src \
  --env HOME=/tmp --env TMPDIR=/tmp --env PYTHONDONTWRITEBYTECODE=1 \
  deye-intercan-checks python -m unittest discover -s tests -v
```

These checks do not flash hardware or prove on-device resource usage, electrical
compatibility, the BMS address, or that diagnostic initialization is unnecessary.

## Sources

- [Original decoder](https://github.com/Psynosaur/esphome-deye-bms/blob/main/deye-can-bus.yaml)
- [ESPHome packages](https://esphome.io/components/packages/)
- [ESP32 CAN modes](https://esphome.io/components/canbus/esp32_can/)
- [Waveshare board](https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN)

The original MIT copyright and permission notice remain in the repository's
[LICENSE](../LICENSE). The original standalone YAML examples remain unchanged.
