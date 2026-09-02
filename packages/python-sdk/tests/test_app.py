from __future__ import annotations

import unittest

from neon3_sdk import NeonApp, ObservableStore


class NeonAppOfflineTests(unittest.TestCase):
    def test_generic_intent_mutates_store_and_advances_revision(self) -> None:
        store = ObservableStore({"selected": None})
        app = NeonApp.offline(
            store=store,
            program={
                "surface_id": "surface.demo",
                "program_revision": {"program_id": "demo", "revision": 1, "schema_version": 1, "capabilities": []},
                "input_schema": {"slots": []},
            },
        )

        @app.intent("domain.select")
        def select(event):
            store.value("selected").set(event.payload["key"])

        outcome = app.run_once(["intent:domain.select:{\"key\":\"alpha\"}"])[0]
        self.assertEqual(outcome.response["status"], "accepted")
        self.assertEqual(store.value("selected").get(), {"kind": "enum", "value": "alpha"})
        self.assertEqual(app.session.input_revision, 1)
        self.assertFalse(store.has_pending_changes())


if __name__ == "__main__":
    unittest.main()
