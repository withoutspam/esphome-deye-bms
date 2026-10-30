"""Validate real ESPHome merges with unrelated UART/Modbus and two BMS instances."""
from pathlib import Path
import base64
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class Loader(yaml.SafeLoader):
    pass


Loader.add_multi_constructor("!", lambda loader, tag, node: loader.construct_scalar(node))


class ConfigurationTests(unittest.TestCase):
    def validate(self, extra="", generate=False):
        with tempfile.TemporaryDirectory(prefix="intercan-config-") as folder:
            root = Path(folder)
            (root / "examples").mkdir()
            (root / "packages").mkdir()
            shutil.copy2(ROOT / "packages/deye-intercan.yaml", root / "packages")
            sample = (ROOT / "examples/secrets.example.yaml").read_text()
            sample = sample.replace("REPLACE_WITH_GENERATED_32_BYTE_BASE64_KEY", base64.b64encode(bytes(range(1, 33))).decode())
            (root / "examples/secrets.yaml").write_text(sample)
            config = (ROOT / "examples/waveshare-intercan.yaml").read_text() + extra
            path = root / "examples/device.yaml"
            path.write_text(config)
            result = subprocess.run([sys.executable, "-m", "esphome", "config", str(path)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if generate:
                generated = subprocess.run([sys.executable, "-m", "esphome", "compile", "--only-generate", str(path)], capture_output=True, text=True, timeout=45)
                self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
                self.assertTrue(list(root.rglob("main.cpp")), "ESPHome did not generate firmware source")
            return yaml.load(result.stdout, Loader=Loader)

    def test_standalone_example(self):
        config = self.validate()
        self.assertEqual(config["esp32"]["framework"]["type"], "esp-idf")
        self.assertEqual(config["canbus"][0]["tx_pin"], 15)
        self.assertEqual(config["canbus"][0]["rx_pin"], 16)
        self.assertEqual(config["canbus"][0]["mode"], "NORMAL")
        self.assertEqual(len(config["sensor"]), 26)
        self.assertEqual(config["canbus"][0]["on_frame"][0]["remote_transmission_request"], False)

    def test_firmware_cpp_generation(self):
        self.validate(generate=True)

    def test_existing_uart_modbus_and_entities_survive_merge(self):
        config = self.validate('''
uart:
  - id: existing_uart
    tx_pin: GPIO17
    rx_pin: GPIO18
    baud_rate: 9600
modbus:
  - id: existing_modbus
    uart_id: existing_uart
    flow_control_pin: GPIO21
modbus_controller:
  - id: existing_inverter
    modbus_id: existing_modbus
    address: 1
    update_interval: 10s
sensor:
  - platform: uptime
    id: existing_uptime
    name: Existing Uptime
''')
        self.assertEqual(config["uart"][0]["tx_pin"]["number"], 17)
        self.assertEqual(config["uart"][0]["rx_pin"]["number"], 18)
        self.assertEqual(config["modbus"][0]["flow_control_pin"]["number"], 21)
        self.assertEqual(config["modbus_controller"][0]["address"], 1)
        self.assertEqual(str(config["modbus_controller"][0]["update_interval"]), "10s")
        ids = {sensor["id"] for sensor in config["sensor"]}
        self.assertIn("existing_uptime", ids)
        self.assertIn("battery_cell_16_voltage", ids)
        self.assertEqual(len(ids), 27)

    def test_two_parameterized_instances_share_one_bus(self):
        extra='''
  second_battery: !include
    file: ../packages/deye-intercan.yaml
    vars:
      bms_id: second
      bms_name: Second Battery
      bms_canbus_id: intercan_bus
      bms_module_address: "2"
      bms_timeout_ms: "45000"
'''
        config = self.validate(extra)
        self.assertEqual(len(config["canbus"]), 1)
        self.assertEqual(len(config["canbus"][0]["on_frame"]), 2)
        self.assertEqual(len(config["sensor"]), 52)
        self.assertEqual(len({item["id"] for item in config["globals"]}), 12)
        ids = {sensor["id"] for sensor in config["sensor"]}
        self.assertIn("battery_cell_01_voltage", ids)
        self.assertIn("second_cell_01_voltage", ids)


if __name__ == "__main__":
    unittest.main()
