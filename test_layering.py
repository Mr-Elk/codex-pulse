import json
import queue
import subprocess
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from active_chat import Binding
from overlay import Overlay, find_context
from context_probe import parse_context
from overlay_geometry import Rect
from snapshot_cache import SnapshotCache
from overlay_stability import Motion
import overlay_style as style


class ContextTests(unittest.TestCase):
    def test_unverified_dialog_input_cannot_replace_composer_geometry(self):
        payload={"composer":{"left":312,"top":747,"right":498,"bottom":766},
                 "composer_source":"unavailable","chat_title":"A","chat_status":"ok","interaction_open":True}
        rect,title,status,popup=parse_context(payload)
        self.assertIsNone(rect)
        self.assertEqual((title,status,popup),("A","ok",True))
        payload["composer_source"]="named"
        self.assertEqual(parse_context(payload)[0],Rect(312,747,498,766))

    def test_popup_signal_is_boolean_and_does_not_require_popup_content(self):
        for value, expected in ((True, True), (False, False), (None, None), ("false", None)):
            with self.subTest(value=value):
                payload = {"composer": {"left": 0, "top": 500, "right": 700, "bottom": 600},
                           "chat_title": "A", "chat_status": "ok", "interaction_open": value}
                completed = SimpleNamespace(returncode=0, stdout=json.dumps(payload))
                with patch("overlay.subprocess.run", return_value=completed):
                    composer, title, status, popup = find_context(100)
                self.assertEqual(composer, Rect(0, 500, 700, 600))
                self.assertEqual((title, status, popup), ("A", "ok", expected))

    def test_failed_probe_is_unknown_instead_of_claiming_popup_closed(self):
        with patch("overlay.subprocess.run", side_effect=subprocess.TimeoutExpired("probe", 4)):
            self.assertEqual(find_context(100), (None, None, "unavailable", None))


class YieldTests(unittest.TestCase):
    def window(self):
        window = Overlay.__new__(Overlay)
        window.args = SimpleNamespace(thread_id="a", preview=False, target_hwnd=None)
        window.target = {"hwnd": 100}
        window.hwnd = 200
        window.win = Mock()
        window.win.user32.IsWindow.return_value = True
        window.win.user32.IsIconic.return_value = False
        window.win.active_target.return_value = True
        window.win.client_rect.return_value = Rect(0, 0, 1000, 800)
        window.win.dpi.return_value = 1
        window.binding = Binding().follow("A", [{"id": "a", "title": "A"}])
        window.bound_title = "A"
        window.snapshot = {"available": True, "usage": {"total_tokens": 123}}
        window.cache = SnapshotCache()
        window.metrics_wake = threading.Event()
        window.context_at = time.monotonic()
        window.motion = Motion(0)
        window.opacity = 255
        window.display_mode = "composer"
        window.desktop_position = None
        window.compact = True
        window.animations = False
        window.avoid_rect = None
        window.applied_bounds = None
        window.placement_context = None
        window.position_updates = 0
        window.settings_panel = None
        window.visible_metrics = style.ORDER
        window.locked, window.passthrough = True, True
        window.win.edit_modifier_down.return_value = False
        window.win.cursor_position.return_value = None
        window.hover_control = None
        window.canvas = Mock()
        window.stop = threading.Event()
        window.results = queue.Queue()
        window.root = Mock()
        window.thread_choice, window.follow_choice, window.menu = Mock(), Mock(), Mock()
        window.composer = Rect(100, 650, 900, 780)
        window.anchor_window_rect = Rect(0, 0, 1000, 800)
        window.anchor_at = time.monotonic()
        window.current_composer = window.composer
        window.last_bounds = Rect(156, 605, 844, 643)
        window.interaction_open = True
        window.visible = True
        window.hidden_reason = None
        window.menu_open = False
        window.drag = None
        window.font_size = 15
        from quota_service import clean_config, METRIC_KEYS
        window.quota_preferences=clean_config(None);window.quota_snapshot={};window.quota_service=None
        window.metric_order=list(METRIC_KEYS);window.strip_visible=True
        window.away_expanded=False;window.compact=False
        window.scale = 1
        window.manual = None
        window.draw = Mock()
        window.write_status = Mock()
        return window

    def context(self, window, popup):
        window.results.put(("context", (100, window.composer, window.anchor_window_rect,
                            time.monotonic(), "A", "ok", [{"id": "a", "title": "A"}], popup)))

    def confirmed_closed(self, window):
        self.context(window, False)
        self.context(window, False)

    def test_popup_detection_keeps_shell_and_metrics_without_clearing_chat(self):
        window = self.window()
        update = {"available":True,"usage":{"total_tokens":456}}
        window.results.put(("snapshot",("a",window.binding.revision,update)))
        window.tick()
        self.assertTrue(window.visible)
        self.assertEqual(window.binding.identity,"a")
        self.assertIs(window.snapshot,update)
        window.win.hide.assert_not_called()

    def test_popup_elsewhere_and_closed_signals_do_not_reposition_the_shell(self):
        window = self.window()
        window.tick()
        window.win.show_without_focus.reset_mock()
        for popup in (False,True,None,False):
            self.context(window,popup)
            window.tick()
        self.assertTrue(window.visible)
        window.win.show_without_focus.assert_not_called()

    def test_one_unknown_probe_briefly_keeps_verified_geometry_and_data(self):
        window = self.window()
        window.tick()
        rect = window.last_bounds
        window.results.put(("context",(100,None,None,time.monotonic(),None,"unavailable",[],None)))
        window.tick()
        self.assertTrue(window.visible)
        self.assertEqual(window.last_bounds,rect)
        self.assertEqual(window.binding.identity,"a")
        self.assertEqual(window.snapshot["usage"]["total_tokens"],123)
        window.win.hide.assert_not_called()

    def test_leaving_app_clears_binding_and_hides_the_attached_shell(self):
        window = self.window()
        window.tick()
        window.win.active_target.return_value = False
        window.tick()
        self.assertIsNone(window.binding.identity)
        self.assertIsNone(window.snapshot)
        self.assertFalse(window.visible)
        self.assertEqual(window.hidden_reason,"host_inactive")

    def test_own_settings_and_drag_keep_the_shell_visible(self):
        window = self.window()
        window.menu_open = True
        window.win.active_target.return_value = False
        window.tick()
        self.assertTrue(window.visible)
        window.win.hide.assert_not_called()


@unittest.skipUnless(sys.platform == "win32", "Native window contract requires Windows")
class NativeLayeringTests(unittest.TestCase):
    def test_helper_is_demoted_before_attaching_owner_and_owner_is_not_modified(self):
        import native_windows as win
        operations = []
        with patch.object(win, "get_long", return_value=0), \
             patch.object(win, "set_long", side_effect=lambda *args: operations.append(("set", args))), \
             patch.object(win.user32, "SetWindowPos", side_effect=lambda *args: operations.append(("position", args))):
            win.decorate_overlay(200, 100)
        self.assertTrue(all(args[0] == 200 for _, args in operations))
        self.assertEqual(operations[1][0], "position")
        self.assertEqual(operations[1][1][1].value, win.W.HWND(-2).value)
        self.assertEqual(operations[2], ("set", (200, -8, 100)))

    def test_placement_keeps_focus_and_does_not_reassert_z_order(self):
        import native_windows as win
        rect = Rect(10, 20, 300, 58)
        with patch.object(win.user32, "SetWindowPos") as position:
            win.show_without_focus(200, rect)
            flags = position.call_args.args[-1]
            self.assertTrue(flags & 0x4)  # preserve z order
            self.assertTrue(flags & 0x10)  # no activate
            win.show_without_focus(200, rect, raise_window=True)
            flags = position.call_args.args[-1]
            self.assertFalse(flags & 0x4)
            self.assertTrue(flags & 0x10)
            self.assertEqual(position.call_args.args[1].value, win.W.HWND(0).value)


if __name__ == "__main__":
    unittest.main()
