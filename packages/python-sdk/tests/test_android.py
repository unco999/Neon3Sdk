"""Android transport contract tests.

Unit tests never touch adb. The integration test (marked with
NEON3_ANDROID_INTEGRATION=1) runs against the real Android host and covers the
whole lifecycle in one case: start (adb forward + health wait),
service.health/describe, and clean shutdown. It skips otherwise so plain
`python -m unittest` never hangs on adb.
"""

from __future__ import annotations

import os
import unittest

from neon3_sdk import AndroidConfig, AndroidSession, NeonClient
from neon3_sdk.errors import RemoteError, TransportError

INTEGRATION = os.environ.get("NEON3_ANDROID_INTEGRATION") == "1"


class AndroidUnitTests(unittest.TestCase):
    def test_endpoint_defaults(self) -> None:
        from neon3_sdk.android import ANDROID_HOST_ENDPOINT, ANDROID_HOST_PORT

        self.assertEqual(ANDROID_HOST_ENDPOINT, "127.0.0.1:43100")
        self.assertEqual(ANDROID_HOST_PORT, 43100)

    def test_client_rejects_non_loopback_unless_allowed(self) -> None:
        with self.assertRaises(ValueError):
            NeonClient.connect("192.168.1.50:43100")
        client = NeonClient.connect("192.168.1.50:43100", allow_non_loopback=True)
        self.assertEqual(client.endpoint, ("192.168.1.50", 43100))

    def test_missing_adb_raises_clear_error(self) -> None:
        config = AndroidConfig(adb="definitely-not-adb-xyz", timeout_seconds=2.0)
        session = AndroidSession(config)
        with self.assertRaises(RuntimeError):
            session.start()


@unittest.skipUnless(INTEGRATION, "set NEON3_ANDROID_INTEGRATION=1 to run against a device")
class AndroidIntegrationTests(unittest.TestCase):
    def test_full_session_lifecycle(self) -> None:
        session = AndroidSession(AndroidConfig(timeout_seconds=20.0))
        handle = session.start()
        self.assertTrue(handle.endpoint)
        self.assertTrue(handle.use_forward)
        client = NeonClient.connect(handle.endpoint, origin="android-contract-test", kind="cli", allow_non_loopback=True)
        health = client.health("wgpu-runtime")
        self.assertEqual(health.status, "healthy")
        describe = client.describe("wgpu-runtime")
        self.assertGreater(describe.epoch, 0)
        session.stop()
        self.assertTrue(session._stopped)


if __name__ == "__main__":
    unittest.main()