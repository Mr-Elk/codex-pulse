"""Navigation/uncertainty boundaries; generation and popup content cannot choose visibility."""
import time
import unittest
from unittest.mock import Mock, patch

from overlay_context import ComposerContext
from context_probe import context_metadata
from overlay_geometry import Rect
import test_layering

RECT = Rect(100,650,900,780)
WINDOW = Rect(0,0,1000,800)
CATALOG = [{"id":"a","title":"A"},{"id":"b","title":"B"}]


class PolicyTests(unittest.TestCase):
    def context(self):
        c = ComposerContext()
        c.observe(100,RECT,WINDOW,10,"A","ok")
        return c

    def test_profile_navigation_invalidates_anchor_even_with_a_stale_composer(self):
        c=self.context()
        self.assertEqual(c.observe(100,RECT,WINDOW,11,"Profile","ok",{"page_kind":"non_work"}),"clear")
        self.assertIsNone(c.composer)
        self.assertEqual(c.reason,"non_work_page")

    def test_new_title_without_composer_never_reuses_previous_anchor(self):
        c=self.context()
        self.assertEqual(c.observe(100,None,WINDOW,11,"B","ok"),"bind")
        self.assertIsNone(c.composer)
        self.assertEqual(c.title,"B")

    def test_unknown_interval_has_a_non_renewable_one_second_deadline(self):
        c=self.context()
        for at in (11,11.4,11.9):
            self.assertEqual(c.observe(100,None,None,at,None,"unavailable"),"hold")
        self.assertFalse(c.expire(12))
        self.assertIsNone(c.composer)

    def test_navigation_cannot_be_resurrected_by_unknown_or_older_observations(self):
        c=self.context();c.observe(100,None,WINDOW,12,"Profile","ok",{"page_kind":"non_work"})
        self.assertEqual(c.observe(100,RECT,WINDOW,11,"A","ok"),"stale")
        c.observe(100,None,None,13,None,"unavailable")
        self.assertFalse(c.expire(13))

    def test_host_change_and_recovery_require_new_verified_anchor(self):
        c=self.context();c.observe(200,None,None,11,None,"unavailable")
        self.assertFalse(c.expire(11))
        c.observe(200,RECT,WINDOW,12,"B","ok")
        self.assertTrue(c.expire(12))

    def test_absence_and_provider_failure_have_distinct_reasons(self):
        c=self.context();c.observe(100,None,WINDOW,11,"A","ok",{"composer_status":"absent"})
        self.assertFalse(c.expire(12));self.assertEqual(c.reason,"no_composer")
        self.assertEqual(context_metadata({"chat_title":"Profile","chat_status":"ok"})["page_kind"],"non_work")
        self.assertEqual(context_metadata({"chat_title":"New work","chat_status":"ok","composer_status":"absent"})["page_kind"],"unknown")

    def test_moving_host_with_same_verified_named_input_is_not_an_unknown_page(self):
        c=self.context()
        moved={"geometry_moved":True,"page_kind":"work","composer_status":"found"}
        for at in (11,12,13):
            self.assertEqual(c.observe(100,None,WINDOW,at,"A","ok",moved),"bind")
            self.assertTrue(c.expire(at));self.assertIsNone(c.uncertain_since)
        c.observe(100,None,WINDOW,14,"B","ok",moved)
        self.assertFalse(c.expire(14))


class OverlayVisibilityTests(unittest.TestCase):
    def window(self):
        return test_layering.YieldTests().window()

    def observe(self,w,title,composer=None,status="ok",metadata=None):
        w.results.put(("context",(100,composer,WINDOW,time.monotonic(),title,status,CATALOG,False,None,metadata or {})))
        w.tick()

    def test_profile_clears_all_anchor_fields_and_hides_native_layers(self):
        w=self.window();w.surface=Mock();w.tick()
        self.observe(w,"Profile",metadata={"page_kind":"non_work"})
        self.assertFalse(w.visible);self.assertIsNone(w.current_composer)
        self.assertIsNone(w.composer);self.assertIsNone(w.anchor_window_rect)
        self.assertEqual(w.hidden_reason,"non_work_page")
        self.assertIsNone(w.binding.identity);w.surface.hide.assert_called_once()

    def test_unknown_timeout_hides_and_clears_but_one_failure_does_not_flash(self):
        w=self.window();w.tick();self.observe(w,None,status="unavailable")
        w.win.hide.assert_not_called();self.assertTrue(w.visible)
        w.context_policy().uncertain_since=time.monotonic()-1.1
        w.tick();self.assertFalse(w.visible);self.assertIsNone(w.snapshot)

    def test_new_page_waits_for_its_own_composer_and_rejects_old_metrics(self):
        w=self.window();w.tick();old=w.binding.revision
        self.observe(w,"B")
        self.assertFalse(w.visible)
        self.assertFalse(w.apply_snapshot("a",{"available":True},old))
        self.observe(w,"B",RECT)
        self.assertTrue(w.visible);self.assertEqual(w.binding.identity,"b")

    def test_generation_and_interrupt_popup_do_not_hide_or_clear_data(self):
        w=self.window();w.snapshot["request_pending"]=True;w.tick()
        snapshot=w.snapshot
        for popup in (True,None,False,True,False):
            w.results.put(("context",(100,RECT,WINDOW,time.monotonic(),"A","ok",CATALOG,popup)))
            w.tick()
        self.assertIs(w.snapshot,snapshot);self.assertTrue(w.visible)
        w.win.hide.assert_not_called()

    def test_repeated_page_switches_restore_without_a_lingering_blank_shell(self):
        w=self.window();w.tick()
        for _ in range(3):
            self.observe(w,"Profile",metadata={"page_kind":"non_work"})
            self.assertFalse(w.visible)
            self.observe(w,"A",RECT)
            self.assertTrue(w.visible)

    def test_desktop_context_loss_clears_identity_without_collapsing_the_strip(self):
        w=self.window();w.display_mode="desktop";w.compact=False
        w.win.work_area.return_value=Rect(0,0,1920,1040);w.save_preferences=Mock()
        self.observe(w,"Profile",metadata={"page_kind":"non_work"})
        self.assertTrue(w.visible);self.assertFalse(w.is_capsule());self.assertFalse(w.compact)
        self.assertIsNone(w.binding.identity)
        self.assertEqual(w.capsule_status(),"未在会话");w.save_preferences.assert_not_called()
        self.observe(w,"A",RECT);self.assertFalse(w.is_capsule())

    def test_fixed_data_is_independent_of_composer_visibility(self):
        for mode in ("composer","desktop"):
            with self.subTest(mode=mode):
                w=self.window();w.binding=w.binding.pin("a","A");snapshot=w.snapshot
                w.display_mode=mode;w.win.work_area.return_value=Rect(0,0,1920,1040)
                self.observe(w,"Profile",metadata={"page_kind":"non_work"})
                self.assertEqual(w.visible,mode=="desktop")
                self.assertEqual(w.binding.identity,"a");self.assertIs(w.snapshot,snapshot)
                if mode=="desktop":self.assertEqual(w.capsule_status(),"固定会话")

    def test_own_settings_keep_only_a_valid_work_context(self):
        w=self.window();w.tick();w.menu_open=True;w.win.active_target.return_value=False
        w.tick();self.assertTrue(w.visible)
        self.observe(w,"Profile",metadata={"page_kind":"non_work"})
        self.assertFalse(w.visible)


if __name__ == "__main__":unittest.main()
