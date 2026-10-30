"""Execute the production YAML lambdas as native C++, with a simulated clock.

The boundary doubles only capture publish_state; decoding and freshness logic
are taken verbatim from the package, not reimplemented in Python.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "deye-intercan.yaml"


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!extend", lambda loader, node: loader.construct_scalar(node))


def load_package(overrides=None):
    if not PACKAGE.exists():
        raise AssertionError("The reusable InterCAN package has not been implemented")
    data = yaml.load(PACKAGE.read_text(), Loader=Loader)
    variables = dict(data["substitutions"])
    variables.update(bms_id="test", bms_name="Test", bms_timeout_ms="1000", bms_max_group_skew_ms="200")
    variables.update(overrides or {})

    def expand(value):
        if isinstance(value, str):
            for key, replacement in variables.items():
                value = value.replace("${" + key + "}", str(replacement))
            return value
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value

    return expand(data)


def harness(data, body):
    declarations = []
    for item in data["globals"]:
        declarations.append(f'{item["type"]} {item["id"]} = {item["initial_value"]};')
    for item in data["sensor"] + data["binary_sensor"]:
        declarations.append(f'Sensor {item["id"]}_storage; Sensor *{item["id"]} = &{item["id"]}_storage;')
    frame = data["canbus"][0]["on_frame"][0]
    decode = frame["then"][0]["lambda"]
    publish = data["script"][0]["then"][0]["lambda"]
    return r'''
#include <array>
#include <vector>
#include <cstdint>
#include <cmath>
#include <algorithm>
#include <cassert>
#include <cstdio>
#define id(x) x
namespace esphome { namespace sensor { struct Sensor { float state = NAN; void publish_state(float value) { state = value; } }; } }
using Sensor = esphome::sensor::Sensor;
uint32_t clock_ms = 0;
uint32_t millis() { return clock_ms; }
''' + "\n".join(declarations) + r'''
void decode(std::vector<uint8_t> x, uint32_t can_id, bool remote_transmission_request) {
''' + decode + r'''
}
void receive(uint32_t can_id, std::vector<uint8_t> x, bool extended = true, bool rtr = false) {
''' + f'if (extended != {str(frame["use_extended_id"]).lower()} || rtr != {str(frame["remote_transmission_request"]).lower()}) return;\n' + r'''
decode(x, can_id, rtr);
}
void publish() {
''' + publish + r'''
}
void near(float got, float want) { assert(std::isfinite(got)); assert(std::fabs(got - want) < 0.002f); }
void full(uint8_t address = 1) {
 receive(0x04008000 | address, {0x0b,0xb8,0x0c,0x1c,0x0c,0x80,0x0c,0xe4});
 receive(0x04018000 | address, {0x0c,0xe4,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4});
 receive(0x04028000 | address, {0x0d,0x48,0x0d,0x48,0x0d,0x48,0x0d,0x48});
 receive(0x04038000 | address, {0x0d,0xac,0x0d,0xb6,0x0d,0xc0,0x0e,0x10});
}
int main() {
''' + body + '\nputs("PASS");\n}\n'


class IntercanTests(unittest.TestCase):
    def run_case(self, body, overrides=None, compile_failure=None):
        source = harness(load_package(overrides), body)
        compiler = shutil.which("clang++") or shutil.which("g++")
        self.assertIsNotNone(compiler, "A C++17 compiler is required")
        with tempfile.TemporaryDirectory(prefix="intercan-test-") as folder:
            cpp = Path(folder) / "test.cpp"
            exe = Path(folder) / "test"
            cpp.write_text(source)
            build = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)], capture_output=True, text=True, timeout=30)
            if compile_failure:
                self.assertNotEqual(build.returncode, 0)
                self.assertIn(compile_failure, build.stderr)
                return
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "PASS")

    def test_startup_is_unavailable(self):
        self.run_case('publish(); assert(std::isnan(test_cell_01_voltage->state)); assert(std::isnan(test_cell_sum_voltage->state)); assert(std::isnan(test_data_age->state)); near(test_fresh_cells->state, 0); near(test_data_complete->state, 0);')

    def test_big_endian_groups_extrema_indices_sum_delta(self):
        self.run_case('full(); publish(); near(test_cell_01_voltage->state, 3.0); near(test_cell_04_voltage->state, 3.3); near(test_cell_09_voltage->state, 3.4); near(test_cell_16_voltage->state, 3.6); near(test_min_cell_voltage->state, 3.0); near(test_max_cell_voltage->state, 3.6); near(test_min_cell_index->state, 1); near(test_max_cell_index->state, 16); near(test_cell_delta->state, 600); near(test_cell_sum_voltage->state, 53.53); near(test_data_complete->state, 1); near(test_valid_frames->state, 4); near(test_fresh_cells->state, 16);')

    def test_equal_extrema_use_first_cell_index(self):
        self.run_case('for (uint32_t group=0; group<4; group++) { receive(0x04008001u + group * 0x10000u, {0x0c,0xe4,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4}); } publish(); near(test_min_cell_index->state, 1); near(test_max_cell_index->state, 1); near(test_cell_delta->state, 0); near(test_cell_sum_voltage->state, 52.8);')

    def test_other_addresses_formats_and_unrelated_ids_are_ignored(self):
        self.run_case('full(2); receive(0x04048001, {1,2}); receive(0x04008001, {1,2}, false); receive(0x04008001, {1,2}, true, true); publish(); near(test_valid_frames->state, 0); near(test_rejected_frames->state, 0); assert(std::isnan(test_cell_01_voltage->state));')

    def test_short_selected_payloads_are_rejected(self):
        self.run_case('receive(0x04008001, {}); receive(0x04008001, {1,2}); publish(); near(test_rejected_frames->state, 2); near(test_valid_frames->state, 0); assert(std::isnan(test_cell_01_voltage->state));')

    def test_bad_voltage_rejects_whole_group_without_refresh(self):
        self.run_case('full(); clock_ms=900; receive(0x04008001, {0x0d,0x48,0x0d,0x48,0,0,0x0d,0x48}); publish(); near(test_cell_01_voltage->state, 3); near(test_rejected_frames->state, 1); near(test_data_age->state, 0.9); clock_ms=1000; publish(); assert(std::isnan(test_cell_01_voltage->state));')

    def test_partial_data_does_not_create_aggregates(self):
        self.run_case('receive(0x04008001, {0x0c,0xe4,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4}); publish(); near(test_cell_01_voltage->state, 3.3); near(test_fresh_cells->state, 4); near(test_data_complete->state, 0); assert(std::isnan(test_min_cell_voltage->state)); assert(std::isnan(test_cell_delta->state));')

    def test_timeout_boundary_and_stale_buffer_not_resurrected(self):
        self.run_case('full(); clock_ms=999; publish(); near(test_data_complete->state, 1); clock_ms=1000; publish(); near(test_data_complete->state, 0); assert(std::isnan(test_cell_16_voltage->state)); receive(0x04008001, {0x0c,0xe4,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4}); publish(); near(test_cell_01_voltage->state, 3.3); assert(std::isnan(test_cell_16_voltage->state)); assert(std::isnan(test_cell_sum_voltage->state)); clock_ms=1100; publish(); near(test_fresh_cells->state, 4);')

    def test_complete_requires_groups_within_skew_window(self):
        self.run_case('full(); clock_ms=201; receive(0x04008001, {0x0c,0xe4,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4}); publish(); near(test_fresh_cells->state, 16); near(test_data_complete->state, 0); assert(std::isnan(test_cell_delta->state));')

    def test_unsigned_clock_rollover(self):
        self.run_case('clock_ms=0xffffff00u; full(); clock_ms += 999u; publish(); near(test_data_complete->state, 1); near(test_data_age->state, 0.999); clock_ms += 1u; publish(); near(test_data_complete->state, 0); assert(std::isnan(test_cell_sum_voltage->state));')

    def test_expired_groups_cannot_reappear_after_full_clock_wrap(self):
        self.run_case('full(); clock_ms=1000; publish(); near(test_data_complete->state, 0); clock_ms=0; publish(); near(test_data_complete->state, 0); assert(std::isnan(test_cell_01_voltage->state)); assert(std::isnan(test_cell_sum_voltage->state));')

    def test_one_active_group_cannot_revive_silent_groups_after_wrap(self):
        self.run_case('full(); clock_ms=1000; receive(0x04008001, {0x0c,0xe4,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4}); publish(); near(test_fresh_cells->state, 4); clock_ms=0; receive(0x04008001, {0x0c,0xe4,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4}); publish(); near(test_fresh_cells->state, 4); near(test_data_complete->state, 0); assert(std::isnan(test_cell_16_voltage->state));')

    def test_address_and_timeout_are_configurable(self):
        self.run_case('full(); full(255); clock_ms=1500; publish(); near(test_valid_frames->state, 4); near(test_data_complete->state, 1); near(test_cell_01_voltage->state, 3.0); clock_ms=2000; publish(); near(test_data_complete->state, 0);', {"bms_module_address":"255", "bms_timeout_ms":"2000"})

    def test_voltage_limits_are_configurable_and_inclusive(self):
        self.run_case('receive(0x04008001, {0x07,0xd0,0x0f,0xa0,0x0c,0xe4,0x0c,0xe4}); publish(); near(test_cell_01_voltage->state, 2); near(test_cell_02_voltage->state, 4); receive(0x04008001, {0x07,0xcf,0x0c,0xe4,0x0c,0xe4,0x0c,0xe4}); publish(); near(test_rejected_frames->state, 1); near(test_cell_01_voltage->state, 2);', {"bms_min_cell_mv":"2000", "bms_max_cell_mv":"4000"})

    def test_invalid_parameters_fail_compilation(self):
        for overrides, message in [({"bms_module_address":"0"}, "module address"), ({"bms_module_address":"256"}, "module address"), ({"bms_timeout_ms":"0"}, "timeout"), ({"bms_timeout_ms":"2147483648"}, "timeout"), ({"bms_max_group_skew_ms":"1001"}, "group skew"), ({"bms_min_cell_mv":"5000"}, "voltage bounds")]:
            with self.subTest(overrides=overrides):
                self.run_case('', overrides, compile_failure=message)


if __name__ == "__main__":
    unittest.main()
