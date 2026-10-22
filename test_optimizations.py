from itertools import combinations
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from active_chat import Binding
from context_probe import PersistentProbe
from overlay import Overlay
import overlay_settings as preferences
import overlay_style as style
from snapshot_cache import SnapshotCache
import test_layering as layering_tests
from test_strip_renderer import SNAPSHOT, decode_png


class CacheTests(unittest.TestCase):
    def test_cached_speed_is_never_current_and_snapshots_are_independent(self):
        now = [10]
        cache = SnapshotCache(clock=lambda: now[0])
        cache.put("a", dict(SNAPSHOT, thread_id="a", request_pending=True))
        restored = cache.restore("a")
        self.assertTrue(restored["from_cache"])
        self.assertIsNone(restored["latest_tps_estimate"])
        self.assertFalse(restored["request_pending"])
        self.assertEqual(style.metrics(restored)["speed"].runs[0].text, "刷新中")
        restored["usage"]["total_tokens"] = 0
        self.assertEqual(cache.restore("a")["usage"]["total_tokens"], SNAPSHOT["usage"]["total_tokens"])
        now[0] = 131
        self.assertIsNone(cache.restore("a"))

    def test_capacity_and_payload_identity_are_enforced(self):
        cache = SnapshotCache(capacity=2)
        cache.put("a", dict(SNAPSHOT, thread_id="wrong"))
        self.assertIsNone(cache.restore("a"))
        for identity in ("a", "b", "c"):
            cache.put(identity, SNAPSHOT)
        self.assertIsNone(cache.restore("a"))
        self.assertIsNone(cache.restore(None))
        self.assertIsNone(cache.restore("unknown"))

    def test_a_b_a_restores_only_verified_identity_and_rejects_old_visit(self):
        window = layering_tests.YieldTests().window()
        window.snapshot = dict(SNAPSHOT, thread_id="a")
        old_revision = window.binding.revision
        window.select_thread("b", "B")
        self.assertIsNone(window.snapshot)
        window.apply_snapshot("b", dict(SNAPSHOT, thread_id="b", usage={"total_tokens": 999}), window.binding.revision)
        window.apply_binding(window.binding.automatic())
        self.assertIsNone(window.snapshot)
        window.apply_binding(window.binding.follow("duplicate", [{"id": "a", "title": "duplicate"}, {"id": "b", "title": "duplicate"}]))
        self.assertIsNone(window.snapshot)
        window.apply_binding(window.binding.follow("A", [{"id": "a", "title": "A"}]))
        self.assertEqual(window.snapshot["usage"]["total_tokens"], SNAPSHOT["usage"]["total_tokens"])
        self.assertTrue(window.snapshot["from_cache"])
        self.assertFalse(window.apply_snapshot("a", dict(SNAPSHOT, usage={"total_tokens": 0}), old_revision))
        self.assertFalse(window.apply_snapshot("a", dict(SNAPSHOT, thread_id="b"), window.binding.revision))

    def test_confirmed_unavailable_source_invalidates_cached_totals(self):
        window = layering_tests.YieldTests().window()
        window.apply_snapshot("a", SNAPSHOT, window.binding.revision)
        window.apply_snapshot("a", {"available": False}, window.binding.revision)
        self.assertIsNone(window.cache.restore("a"))


class SelectionAndSettingsTests(unittest.TestCase):
    def test_machine_pointer_keeps_explorer_and_packaged_launches_on_one_settings_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / "physical" / "CodexPulse" / "settings.json"
            actual.parent.mkdir(parents=True)
            (root / ".codex-pulse-local.json").write_text(json.dumps({"settings_file": str(actual)}))
            with patch.object(preferences, "__file__", str(root / "overlay_settings.py")):
                self.assertEqual(preferences.default_path(), actual.resolve())

    def test_invalid_machine_pointer_does_not_redirect_default_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex-pulse-local.json").write_text('{"settings_file":"relative/settings.json"}')
            with patch.object(preferences, "__file__", str(root / "overlay_settings.py")), patch.dict("os.environ", {"LOCALAPPDATA": str(root)}):
                self.assertEqual(preferences.default_path(), (root / "CodexPulse" / "settings.json").resolve())

    def test_v1_migration_preserves_position_font_and_exact_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "settings.json"
            original = b'{"version":1,"font_size":13,"position":{"anchor":"composer","center_ratio":0.4,"gap":24},"custom_note":"keep"}'
            file.write_bytes(original)
            loaded = preferences.load(file)
            self.assertTrue(loaded["locked"])
            preferences.save(file, loaded["font_size"], loaded["position"], False, ["speed", "tokens"])
            reloaded = preferences.load(file)
            self.assertEqual((reloaded["font_size"], reloaded["position"]), (loaded["font_size"], loaded["position"]))
            self.assertFalse(reloaded["locked"])
            self.assertEqual(reloaded["visible_metrics"], ["speed", "tokens"])
            self.assertEqual(file.with_name("settings.v1.backup.json").read_bytes(), original)
            self.assertEqual(json.loads(file.read_text())["custom_note"], "keep")
            preferences.save(file, 17, None, True, ["context"])
            self.assertEqual(file.with_name("settings.v1.backup.json").read_bytes(), original)

    def test_invalid_selection_and_lock_values_recover_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "settings.json"
            file.write_text('{"locked":"false","visible_metrics":["not-a-metric"]}')
            loaded = preferences.load(file)
            self.assertTrue(loaded["locked"])
            self.assertEqual(loaded["visible_metrics"], list(style.ORDER))

    def test_failed_migration_backup_does_not_overwrite_original_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "settings.json"
            original = b'{"version":1,"font_size":13}'
            file.write_bytes(original)
            real_open = Path.open
            def open_file(path, *args, **kwargs):
                if path.name == "settings.v1.backup.json":
                    raise PermissionError("simulated backup failure")
                return real_open(path, *args, **kwargs)
            with patch.object(Path, "open", new=open_file), self.assertRaises(PermissionError):
                preferences.save(file, 17, None)
            self.assertEqual(file.read_bytes(), original)

    def test_all_nonempty_subsets_keep_order_and_shrink_width(self):
        self.assertEqual(style.width_for(), style.WIDTH)
        for size in range(1, len(style.ORDER) + 1):
            for selected in combinations(style.ORDER, size):
                width = style.width_for(selected)
                self.assertLessEqual(width, style.WIDTH)
                self.assertEqual(tuple(style.metrics(dict(SNAPSHOT, visible_metrics=selected))), selected)
                self.assertEqual(tuple(c.key for c in style.columns(width, selected=selected)), selected)
                self.assertEqual(style.columns(10, selected=selected), [])

    def test_cannot_hide_the_last_metric_from_the_menu(self):
        window = layering_tests.YieldTests().window()
        window.visible_metrics = ("tokens",)
        window.metric_choices = {key: Mock(get=Mock(return_value=False)) for key in style.ORDER}
        window.save_preferences = Mock()
        window.select_metrics()
        self.assertEqual(window.visible_metrics, ("tokens",))
        window.metric_choices["tokens"].set.assert_called_once_with(True)
        window.save_preferences.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Exact renderer needs Windows")
    def test_every_selected_subset_renders_without_clipping(self):
        from strip_renderer import render
        for size in range(1, len(style.ORDER) + 1):
            for selected in combinations(style.ORDER, size):
                with self.subTest(selected=selected):
                    width = style.width_for(selected)
                    png, layout = render(dict(SNAPSHOT, visible_metrics=selected), width)
                    dimensions, rows = decode_png(png)
                    self.assertEqual(dimensions[:2], (width, style.HEIGHT))
                    self.assertEqual(tuple(c["key"] for c in layout), selected)
                    self.assertTrue(all(c["text_right"] <= c["right"] - 9 for c in layout))


class PersistentWorkerTests(unittest.TestCase):
    def helper(self, delay=0):
        program = ("import sys,json,time\n"
                   "for command in sys.stdin:\n"
                   f" time.sleep({delay})\n"
                   " print(json.dumps({'chat_title':'A','chat_status':'ok','interaction_open':False}),flush=True)\n")
        return PersistentProbe(command_factory=lambda hwnd: [sys.executable, "-u", "-c", program])

    def test_multiple_probes_reuse_one_process_and_eof_shuts_it_down(self):
        probe = self.helper()
        try:
            for _ in range(3):
                self.assertEqual(probe.read(100)[1:], ("A", "ok", False))
            process = probe.process
            self.assertEqual((probe.starts, probe.requests), (1, 3))
        finally:
            probe.close()
        self.assertIsNotNone(process.poll())

    def test_observation_timeout_keeps_same_process_and_inflight_request(self):
        probe = self.helper(delay=0.2)
        try:
            self.assertEqual(probe.read(100, timeout=0.01), (None, None, "unavailable", None))
            pid = probe.process.pid
            self.assertEqual(probe.read(100, timeout=2)[1:], ("A", "ok", False))
            self.assertEqual((probe.process.pid, probe.starts, probe.requests), (pid, 1, 1))
        finally:
            probe.close()

    def test_context_is_emitted_while_metrics_are_blocked(self):
        window = layering_tests.YieldTests().window()
        started, release = threading.Event(), threading.Event()
        def slow_snapshot():
            started.set()
            release.wait(3)
            return SNAPSHOT
        monitor = Mock(snapshot=Mock(side_effect=slow_snapshot))
        window.args.codex_home = Path(tempfile.gettempdir())
        window.probe = Mock(read=Mock(return_value=(window.composer, "A", "ok", True)))
        metric_worker = threading.Thread(target=window.collect_metrics)
        context_worker = threading.Thread(target=window.collect_context)
        try:
            with patch("overlay.Monitor", return_value=monitor), patch("overlay.thread_catalog.CatalogCache.read", return_value=[{"id": "a", "title": "A"}]):
                metric_worker.start()
                self.assertTrue(started.wait(2))
                context_worker.start()
                kind, payload = window.results.get(timeout=2)
                self.assertEqual(kind, "context")
                self.assertTrue(payload[-1])
                self.assertFalse(release.is_set())
                window.stop.set()
                release.set()
                window.metrics_wake.set()
                metric_worker.join(3)
                context_worker.join(3)
        finally:
            window.stop.set()
            release.set()
            window.metrics_wake.set()
        self.assertFalse(metric_worker.is_alive())
        self.assertFalse(context_worker.is_alive())


class InputModeTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Native focus contract needs Windows")
    def test_startup_restores_exact_previous_focus_only_if_our_window_took_it(self):
        import native_windows as win
        with patch.object(win.user32, "GetForegroundWindow", return_value=200), \
             patch.object(win.user32, "IsWindow", return_value=True), \
             patch.object(win.user32, "IsWindowVisible", return_value=True), \
             patch.object(win.user32, "IsIconic", return_value=False), \
             patch.object(win.user32, "ShowWindow"), \
             patch.object(win, "get_long", return_value=100), \
             patch.object(win.user32, "SetForegroundWindow", return_value=True) as restore:
            self.assertTrue(win.restore_startup_focus(200, 100))
            restore.assert_called_once_with(100)
            restore.reset_mock()
            with patch.object(win.user32, "GetForegroundWindow", return_value=300):
                self.assertFalse(win.restore_startup_focus(200, 100))
            with patch.object(win.user32, "GetForegroundWindow", side_effect=[200, 300]):
                self.assertFalse(win.restore_startup_focus(200, 100))
            with patch.object(win.user32, "IsIconic", return_value=True):
                self.assertFalse(win.restore_startup_focus(200, 100))
            self.assertFalse(win.restore_startup_focus(200, None))
            restore.assert_not_called()

    def test_visible_edge_controls_work_without_unlocking_or_keyboard_modifiers(self):
        window = layering_tests.YieldTests().window()
        rect = window.last_bounds
        for x, control, cursor in ((rect.left+10, "drag", "fleur"),
                                   (rect.right-10, "menu", "hand2"),
                                   (rect.left+100, None, "")):
            with self.subTest(control=control):
                window.win.cursor_position.return_value = (x, rect.top+10)
                window.refresh_input_mode(True)
                self.assertEqual(window.hover_control, control)
                self.assertEqual(window.passthrough, control is None)
                window.canvas.configure.assert_called_with(cursor=cursor)
                self.assertTrue(window.locked)

    def test_control_hit_regions_follow_font_and_dpi_and_reject_outside_points(self):
        for scale in (13/15, 1, 1.5, 17/15*2):
            edge = round(style.INSET*scale)
            self.assertEqual(style.control_at(edge-1, 10, 600, 38, scale), "drag")
            self.assertIsNone(style.control_at(edge, 10, 600, 38, scale))
            self.assertEqual(style.control_at(600-edge, 10, 600, 38, scale), "menu")
            for point in ((-1, 10), (600, 10), (10, -1), (10, 38)):
                self.assertIsNone(style.control_at(*point, 600, 38, scale))

    def test_hidden_or_inactive_strip_does_not_enable_controls_from_mouse_position(self):
        window = layering_tests.YieldTests().window()
        window.win.cursor_position.return_value = (window.last_bounds.left+10, window.last_bounds.top+10)
        window.visible = False
        window.refresh_input_mode(True)
        self.assertTrue(window.passthrough)
        window.visible = True
        window.refresh_input_mode(False)
        self.assertTrue(window.passthrough)
        window.win.cursor_position.assert_not_called()

    def test_locked_handle_starts_drag_but_metric_cells_cannot_start_one(self):
        window = layering_tests.YieldTests().window()
        window.passthrough = False
        window.height = 38
        window.canvas.winfo_width.return_value = window.last_bounds.width
        event = type("Event", (), {"x": 10, "y": 10,
                                  "x_root": window.last_bounds.left+10,
                                  "y_root": window.last_bounds.top+10})()
        window.drag_start(event)
        self.assertEqual(window.drag, (10, 10))
        window.drag = None
        event.x = 100
        window.drag_start(event)
        self.assertIsNone(window.drag)

    def test_probe_changes_cannot_hide_a_drag_in_progress(self):
        for popup in (True, None):
            with self.subTest(popup=popup):
                window = layering_tests.YieldTests().window()
                window.interaction_open = popup
                window.drag = (10, 10)
                window.tick()
                self.assertTrue(window.visible)
                self.assertFalse(window.passthrough)
                window.win.hide.assert_not_called()
                window.root.geometry.assert_not_called()

    def test_close_cancels_own_callbacks_and_is_idempotent(self):
        window = layering_tests.YieldTests().window()
        window.probe = Mock()
        window.root.tk.call.return_value = ("after#1", "after#2")
        window.close()
        window.close()
        window.root.after_cancel.assert_any_call("after#1")
        window.root.after_cancel.assert_any_call("after#2")
        window.root.destroy.assert_called_once()
        window.probe.close.assert_called_once()

    def test_locked_passthrough_temporary_edit_drag_and_menu(self):
        window = layering_tests.YieldTests().window()
        window.passthrough = None
        window.refresh_input_mode(True)
        self.assertTrue(window.passthrough)
        window.win.edit_modifier_down.return_value = True
        window.refresh_input_mode(True)
        self.assertFalse(window.passthrough)
        window.win.edit_modifier_down.return_value = False
        window.menu_open = True
        window.refresh_input_mode(True)
        self.assertFalse(window.passthrough)
        window.menu_open = False
        window.drag = (1, 2)
        window.refresh_input_mode(True)
        self.assertFalse(window.passthrough)
        window.drag = None
        window.refresh_input_mode(True)
        self.assertTrue(window.passthrough)
        self.assertTrue(window.locked)

    @unittest.skipUnless(sys.platform == "win32", "Native window contract needs Windows")
    def test_mouse_transparency_preserves_no_activate_and_uses_full_opacity(self):
        import native_windows as win
        original = 0x08000080
        with patch.object(win, "get_long", return_value=original), patch.object(win, "set_long") as setter, patch.object(win.user32, "SetLayeredWindowAttributes", return_value=True) as alpha:
            win.set_passthrough(200, True)
            flags = setter.call_args.args[2]
            self.assertEqual(flags & original, original)
            self.assertTrue(flags & 0x80000 and flags & 0x20)
            alpha.assert_called_with(200, 0, 255, 2)
            win.set_passthrough(200, False)
            self.assertFalse(setter.call_args.args[2] & 0x20)

    @unittest.skipUnless(sys.platform == "win32", "Native target selection needs Windows")
    def test_explicit_target_is_verified_even_while_minimized(self):
        import native_windows as win
        verified = {"hwnd": 123, "pid": 456, "app": "chatgpt.exe"}
        with patch.object(win, "window_metadata", return_value=verified) as lookup, patch.object(win, "app_windows") as automatic:
            self.assertEqual(win.select_window(123), verified)
            lookup.assert_called_once_with(123, allow_minimized=True)
            automatic.assert_not_called()


if __name__ == "__main__":
    unittest.main()
