# Deye BMS for ESPHome

This fork adds a reusable **16-cell InterCAN voltage-monitoring package** that
can share a device with an existing RS485/Modbus integration. It extends a CAN
controller supplied by the device configuration and does not define a board,
UART, Wi-Fi, API, OTA, or application-level CAN transmissions.

- [Package and configuration guide](docs/intercan.md)
- [Waveshare ESP32-S3-RS485-CAN example](examples/waveshare-intercan.yaml)
- [Example secrets](examples/secrets.example.yaml) — copy to `examples/secrets.yaml`
  and replace every example value before installation.
- [Tests](tests/): native C++ execution of the production lambdas and ESPHome
  configuration-merge tests.

The map is derived from upstream RW-M6.1 / SE-G5.1Pro voltage frames.
**SE-F16 has not been verified on hardware.** The package does not automatically
start a diagnostic stream; see the guide's ACK/initialization discussion.

The upstream standalone configurations and MIT license are preserved below.

---

## Original project notes

## ESPhome Deye batteries

### Prerequisites 
  - PCS CAN BUS: Baudrate: 500K => ESP32 + CAN Transceiver board TJA1050 or SN65HVD230
  - InterCan CAN BUS: Baudrate: 250K => MCP2515 over SPI

#### We run two CAN LAN cables
 - PCS which gives array summary information
   - We use a RJ45 splitter so that the inverter maintains communication with the top computer BMS
 - InterCAN which gives more specific information like cell voltages

![image](https://github.com/user-attachments/assets/028cd742-215c-413f-8b7b-e5a3d417ff13)

## Home Assistant has a lot of entities for these 2 batteries 
![entities](https://i.imgur.com/LPiuXJV.png)
  - 142 for only pack 1 and 59 for each pack thereafter
  - CAN ID: 0x110 was only partially integrated
    - Bytes 0 to 6 were skipped, which is another 56 entities per pack ``:O``
   
## Connection diagrams from [esphome.io](https://esphome.io)
[check it out on the wiki](https://github.com/Psynosaur/esphome-deye-bms/wiki#connection-diagram)

## Thanks
 - [Adminius](https://github.com/Adminius/esphome-yaml-collection/blob/main/deye_rw-m6.1.yaml) for the work on PCS :)
