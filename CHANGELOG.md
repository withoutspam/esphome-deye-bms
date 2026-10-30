# Changelog

## Modular InterCAN v1 — 2026-10-30

- Add a reusable YAML package for one 16-cell module, extending caller-owned CAN.
- Add configurable module address, entity prefixes, publication, expiry, group skew
  and voltage sanity bounds; multiple instances may share one controller.
- Add cell voltages, derived extrema/indices/sum/delta and freshness diagnostics.
- Reject malformed callback payloads atomically; latch expiry across clock rollover.
- Add a Waveshare ESP32-S3 ESP-IDF example with NORMAL acknowledgments and encrypted
  API/OTA. The decoder includes no application-level transmit actions.
- Preserve upstream examples and MIT license.

Validation: 19 tests exercise actual C++ lambda bodies, parameter bounds, clock
rollover and stale buffers, plus ESPHome 2026.10.1 validation/firmware source
generation, existing UART/Modbus and two BMS instances. Tests run in a network-free
container with the repository read-only and bounded resources.

Limits: no full ESP32 cross-compilation or hardware acceptance. SE-F16 mapping,
address, bitrate, wiring and diagnostic initialization remain unverified. ESPHome
normalizes raw CAN DLC above eight; the package validates callback payload length,
not raw DLC. See [the guide](docs/intercan.md) before installation.
