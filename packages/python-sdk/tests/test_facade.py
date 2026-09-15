"""Tests for the React-hooks-style façade (neon3_sdk.facade)."""

from __future__ import annotations

import unittest

from neon3_sdk.app import NeonApp
from neon3_sdk.facade import FacadeApp, State, _current, mount, on, start, state


def _offline_app() -> FacadeApp:
    """Build a FacadeApp wrapping an offline (no-runtime) NeonApp for tests."""
    neon = NeonApp.offline(origin="facade-test")
    return FacadeApp(neon)


class FacadeContextTest(unittest.TestCase):
    def test_no_active_app_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            _current()

    def test_context_manager_pushes_and_pops(self) -> None:
        app = _offline_app()
        with app:
            self.assertIs(_current(), app)
            s = state(0)
            self.assertIsInstance(s, State)
            self.assertEqual(s.value, 0)
        # after exit, no active app
        with self.assertRaises(RuntimeError):
            _current()


class StateTest(unittest.TestCase):
    def test_state_set_marks_store_dirty(self) -> None:
        app = _offline_app()
        with app:
            s = state(0)
            self.assertEqual(s.value, 0)
            s.value = 42
            self.assertEqual(s.value, 42)
            self.assertIn("state_1", app.store._dirty_scalars)

    def test_state_auto_key_increments(self) -> None:
        app = _offline_app()
        with app:
            a = state(0)
            b = state("hello")
            self.assertEqual(a.key, "state_1")
            self.assertEqual(b.key, "state_2")

    def test_state_explicit_node(self) -> None:
        app = _offline_app()
        with app:
            s = state(0, node="counter")
            self.assertEqual(s.key, "counter")

    def test_state_iadd(self) -> None:
        app = _offline_app()
        with app:
            s = state(0)
            s += 1
            s += 1
            self.assertEqual(s.value, 2)


class OnTest(unittest.TestCase):
    def test_on_registers_and_dispatches(self) -> None:
        app = _offline_app()
        with app:
            called: list[str] = []

            @on("btn.increment")
            def _():
                called.append("clicked")

            # The decorator should have registered with the router
            self.assertIn("btn.increment", app.neon.router._exact)  # type: ignore[attr-defined]
            # Calling the registered handler directly should work
            handler = app.neon.router._exact["btn.increment"]  # type: ignore[attr-defined]
            handler()
            self.assertEqual(called, ["clicked"])

    def test_on_with_payload(self) -> None:
        app = _offline_app()
        with app:
            received: list[dict] = []

            @on("slider.change")
            def _(event):
                received.append(getattr(event, "payload", {}))

            self.assertIn("slider.change", app.neon.router._exact)  # type: ignore[attr-defined]
            handler = app.neon.router._exact["slider.change"]  # type: ignore[attr-defined]
            # Simulate an event with a payload
            class _Ev:
                payload = {"value": 0.5}
            handler(_Ev())
            self.assertEqual(received, [{"value": 0.5}])


class ShaderNamespaceTest(unittest.TestCase):
    def test_shader_on_registers_handler(self) -> None:
        app = _offline_app()
        with app:
            received: list[list[float]] = []

            @app.shader.on(0xDEADBEEF)
            def _(payload):
                received.append(payload)

            self.assertIn(0xDEADBEEF, app._shader_handlers)
            handler = app._shader_handlers[0xDEADBEEF]
            handler([1.0, 2.0, 3.0, 4.0])
            self.assertEqual(received, [[1.0, 2.0, 3.0, 4.0]])


class RendererNamespaceTest(unittest.TestCase):
    def test_view_extras_validation(self) -> None:
        app = _offline_app()
        with app:
            with self.assertRaises(ValueError):
                app.renderer.view_extras()
            with self.assertRaises(ValueError):
                app.renderer.view_extras(*([0.0, 0.0, 0.0, 0.0] * 11))
            with self.assertRaises(ValueError):
                app.renderer.view_extras([1.0, 2.0, 3.0])


class AnimNamespaceTest(unittest.TestCase):
    def test_anim_without_renderer_raises(self) -> None:
        app = _offline_app()
        with app:
            with self.assertRaises(Exception):
                app.anim.pause("hero.timeline")


class SurfaceNamespaceTest(unittest.TestCase):
    def test_surface_render_offline_raises(self) -> None:
        """Offline app has no render client; render() should raise clearly."""
        app = _offline_app()
        with app:
            with self.assertRaises(RuntimeError):
                app.surface.render("hello.nui")


class PngTest(unittest.TestCase):
    def test_png_path_property(self) -> None:
        from neon3_sdk.facade import PNG
        png = PNG("/tmp/fake.png")
        self.assertEqual(png.path, "/tmp/fake.png")


if __name__ == "__main__":
    unittest.main()
