import unittest

from app.engines.runtime_accel import (
    CPU_PROVIDERS,
    detect_accel,
    is_accel_provider_list,
    list_accel_providers,
    resolve_providers,
)


class RuntimeAccelTests(unittest.TestCase):
    def test_cpu_default_when_prefer_off(self):
        self.assertEqual(resolve_providers(False), CPU_PROVIDERS)

    def test_force_cpu_overrides_prefer(self):
        self.assertEqual(
            resolve_providers(True, force_cpu=True),
            CPU_PROVIDERS,
        )

    def test_detect_returns_status(self):
        status = detect_accel()
        self.assertIsInstance(status.available, bool)
        self.assertTrue(status.summary)
        self.assertTrue(status.detail)
        # This machine (CI/dev) may only have CPU — still valid
        if not status.available:
            self.assertEqual(resolve_providers(True), CPU_PROVIDERS)

    def test_is_accel_provider_list(self):
        self.assertFalse(is_accel_provider_list(CPU_PROVIDERS))
        self.assertFalse(is_accel_provider_list([]))
        self.assertTrue(
            is_accel_provider_list(
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
            )
        )

    def test_list_accel_filters_unknown(self):
        fake = ["CPUExecutionProvider", "CUDAExecutionProvider", "SomethingElse"]
        self.assertEqual(list_accel_providers(fake), ["CUDAExecutionProvider"])


if __name__ == "__main__":
    unittest.main()
