"""User interaction regressions, using isolated overlay owners and local settings."""
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from active_chat import Binding
from overlay_geometry import Rect
import test_layering as layering


class QuickInteractionTests(unittest.TestCase):
    def owner(self, mode="composer", compact=True, scale=1):
        owner = layering.YieldTests().window()
        owner.display_mode, owner.compact, owner.scale = mode, compact, scale
        owner.expanded_mode = mode
        owner.passthrough = False
        owner.save_preferences = Mock()
        owner.win.work_area.return_value = Rect(0, 0, 1920, 1040)
        return owner

    def press(self, owner, x=10, y=20):
        rect = owner.last_bounds
        event = SimpleNamespace(x=x, y=y, x_root=rect.left+x, y_root=rect.top+y)
        owner.win.cursor_position.return_value = (event.x_root,event.y_root)
        owner.refresh_input_mode(True)
        owner.drag_start(event)
        return event

    def test_grip_click_roundtrips_composer_and_capsule_twenty_times(self):
        owner = self.owner()
        position = {"anchor":"composer", "center_ratio":.4, "gap":16}
        owner.manual = position.copy()
        for index in range(20):
            owner.drag_end(self.press(owner))
            self.assertEqual(owner.display_mode, "desktop" if index % 2 == 0 else "composer")
            self.assertTrue(owner.compact)
            self.assertEqual(owner.manual, position)
            self.assertEqual(owner.binding.identity, "a")
            self.assertTrue(owner.visible)
        owner.win.hide.assert_not_called()

    def test_desktop_full_and_capsule_roundtrip_without_changing_mode(self):
        owner = self.owner("desktop", False)
        for index in range(12):
            owner.drag_end(self.press(owner))
            self.assertEqual(owner.compact, index % 2 == 0)
            self.assertEqual(owner.display_mode, "desktop")

    def test_small_pointer_jitter_does_not_move_or_save_a_drag_position(self):
        owner = self.owner(scale=2)
        event = self.press(owner)
        before = owner.last_bounds
        event.x_root += 3
        event.y_root += 2
        owner.drag_move(event)
        self.assertEqual(owner.last_bounds, before)
        owner.drag_end(event)
        self.assertEqual(owner.display_mode, "desktop")
        self.assertIsNone(owner.manual)

    def test_real_drag_never_collapses_or_changes_mode_at_each_dpi(self):
        for mode in ("composer", "desktop"):
            for scale in (1, 1.5, 2):
                with self.subTest(mode=mode, scale=scale):
                    owner = self.owner(mode, False, scale)
                    event = self.press(owner)
                    event.x_root += round(30*scale)
                    owner.drag_move(event)
                    owner.drag_end(event)
                    self.assertEqual(owner.display_mode, mode)
                    self.assertFalse(owner.compact)
                    self.assertIsNotNone(owner.manual if mode=="composer" else owner.desktop_position)
                    owner.win.hide.assert_not_called()

    def test_release_movement_is_not_mistaken_for_click_when_motion_event_is_missing(self):
        owner = self.owner()
        event = self.press(owner)
        before = owner.last_bounds
        event.x_root += 50
        owner.drag_end(event)
        self.assertEqual(owner.display_mode, "composer")
        self.assertEqual(owner.last_bounds.left, before.left+50)
        self.assertIsNotNone(owner.manual)

    def test_pending_manual_mode_accepts_repeated_clicks_and_rejects_old_results(self):
        owner = self.owner()
        owner.binding = Binding()
        owner.follow_choice = SimpleNamespace(get=lambda: False, set=lambda _:None)
        old_revision = owner.binding.revision
        for _ in range(12):
            owner.follow_choice.get = lambda: True
            owner.toggle_follow()
            self.assertEqual(owner.binding.mode, "auto")
            owner.follow_choice.get = lambda: False
            owner.toggle_follow()
            self.assertEqual(owner.binding.mode, "fixed")
            self.assertIsNone(owner.binding.identity)
            self.assertFalse(owner.apply_snapshot("a", {"available":True}, old_revision))
            self.assertIs(owner.binding.follow("A", [{"id":"a","title":"A"}]), owner.binding)

    def test_closing_host_preserves_an_explicitly_fixed_desktop_session(self):
        owner = self.owner("desktop")
        owner.binding = Binding().pin("a", "A")
        owner.win.user32.IsWindow.return_value = False
        owner.win.select_window.return_value = None
        owner.next_target_probe = 0
        owner.tick()
        self.assertEqual((owner.binding.mode,owner.binding.identity), ("fixed","a"))
        self.assertTrue(owner.visible)


if __name__ == "__main__":
    unittest.main()
