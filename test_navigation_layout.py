import unittest,time
from unittest.mock import patch
from overlay_geometry import Rect
from navigation_layout import NavigationLayout
import test_layering as fixture
from product_strip import displayed_metrics

WINDOW=Rect(0,0,1920,1032);NARROW=Rect(291,914,818,1028);WIDE=Rect(719,914,1488,1012);SHELL=Rect(315,874,521,914)

class NavigationLayoutTests(unittest.TestCase):
    def layout(self):
        n=NavigationLayout();n.observe(1,'A',NARROW,WINDOW,10,SHELL,True);return n
    def test_two_second_side_panel_restore_never_targets_intermediate_wide_input(self):
        n=self.layout()
        for at in (11,11.4,12,12.5,13):
            n.observe(1,'B',WIDE,WINDOW,at,SHELL,True)
            self.assertEqual(n.presentation(WINDOW,40,at),SHELL)
        n.observe(1,'B',NARROW,WINDOW,13.2,SHELL,True)
        self.assertIsNone(n.presentation(WINDOW,40,13.2));self.assertEqual(n.composer,NARROW)
    def test_guard_catches_reflow_after_first_new_title_still_has_old_shape(self):
        n=self.layout();n.observe(1,'B',NARROW,WINDOW,11,SHELL,True)
        self.assertFalse(n.holding(11));n.observe(1,'B',WIDE,WINDOW,11.3,SHELL,True)
        self.assertTrue(n.holding(11.3));self.assertEqual(n.presentation(WINDOW,40,11.3),SHELL)
    def test_model_footer_height_does_not_delay_release_of_restored_panel(self):
        n=self.layout();n.observe(1,'B',WIDE,WINDOW,11,SHELL,True)
        n.observe(1,'B',Rect(291,914,818,1012),WINDOW,12.5,SHELL,True)
        self.assertFalse(n.holding(12.5));self.assertIsNone(n.presentation(WINDOW,40,12.5))
    def test_real_new_layout_commits_once_at_a_bounded_nonrenewable_deadline(self):
        n=self.layout();n.observe(1,'B',WIDE,WINDOW,11,SHELL,True)
        for at in (12,13,13.9):n.observe(1,'B',WIDE,WINDOW,at,SHELL,True)
        self.assertEqual(n.until,14)
        n.observe(1,'B',WIDE,WINDOW,14.01,SHELL,True)
        self.assertFalse(n.holding(14.01));self.assertEqual(n.composer,WIDE)
    def test_unknown_geometry_leaves_switching_for_neutral_waiting_until_verified(self):
        n=self.layout();n.observe(1,'B',None,WINDOW,11,SHELL,True)
        n.observe(1,None,None,None,13.9,SHELL,None)
        self.assertEqual(n.presentation(WINDOW,40,13.9),SHELL)
        self.assertEqual(n.presentation(WINDOW,40,14),SHELL);self.assertFalse(n.holding(14));self.assertTrue(n.waiting)
        n.observe(1,'B',None,WINDOW,20,SHELL,True);self.assertEqual(n.until,14)
        n.observe(1,'B',NARROW,WINDOW,21,SHELL,True);self.assertFalse(n.waiting);self.assertIsNone(n.presentation(WINDOW,40,21))
    def test_host_resize_nonwork_and_new_host_cancel_the_hold(self):
        for mode in ('resize','nonwork','host'):
            n=self.layout();n.observe(1,'B',WIDE,WINDOW,11,SHELL,True)
            if mode=='resize':self.assertIsNone(n.presentation(Rect(0,0,1280,820),40,11.1))
            elif mode=='nonwork':n.observe(1,'Profile',None,WINDOW,11.1,SHELL,False)
            else:n.observe(2,'C',NARROW,WINDOW,11.1,SHELL,True)
            self.assertFalse(n.holding(11.1))
    def test_rapid_navigation_preserves_one_shell_and_stale_results_cannot_restore_it(self):
        n=self.layout();n.observe(1,'B',WIDE,WINDOW,11,SHELL,True);n.observe(1,'C',WIDE,WINDOW,11.5,SHELL,True)
        n.observe(1,'A',NARROW,WINDOW,10.5,SHELL,True)
        self.assertEqual(n.title,'C');self.assertEqual(n.presentation(WINDOW,40,12),SHELL)
    def test_transition_metrics_exclude_all_old_session_values(self):
        s={'navigation_pending':True,'available':True,'visible_metrics':['speed','tokens','quota','recent'],'latest_tps_estimate':999,'usage':{'total_tokens':999999},'quota_display':{'quota':'79%','recent':'3%'}}
        for compact in (True,False):
            values=displayed_metrics({**s,'capsule':compact})
            self.assertEqual(next(iter(values)),'transition');self.assertFalse(set(values)&{'speed','tokens','cache','context','rounds'})
            self.assertEqual(values['transition'].runs[0].text,'切换中')
            waiting=displayed_metrics({**s,'capsule':compact,'navigation_waiting':True})
            self.assertEqual(waiting['transition'].runs[0].text,'待识别')
            self.assertFalse(set(waiting)&{'speed','tokens','cache','context','rounds'})
    def test_waiting_neutral_shell_cannot_survive_nonwork_or_moving_host(self):
        for cause in ('nonwork','resize','host'):
            n=self.layout();n.observe(1,'B',None,WINDOW,11,SHELL,True)
            self.assertEqual(n.presentation(WINDOW,40,20),SHELL);self.assertTrue(n.waiting)
            if cause=='nonwork':n.observe(1,'Profile',None,WINDOW,21,SHELL,False)
            elif cause=='host':n.observe(2,'C',None,WINDOW,21,SHELL,True)
            else:n.presentation(Rect(0,0,1280,820),40,21)
            self.assertFalse(n.showing(21))
    def test_overlay_keeps_live_shell_without_reusing_new_chat_composer_or_old_metrics(self):
        w=fixture.YieldTests().window();w.tick()
        catalog=[{'id':'a','title':'A'},{'id':'b','title':'B'}];at=time.monotonic()
        w.results.put(('context',(100,w.composer,w.anchor_window_rect,at,'A','ok',catalog,False,None,{})));w.tick();before=w.last_bounds;revision=w.binding.revision
        w.results.put(('context',(100,None,w.anchor_window_rect,at+.01,'B','ok',catalog,False,None,{})));w.tick()
        self.assertTrue(w.visible);self.assertTrue(w.layout_transition);self.assertEqual(w.last_bounds.left,before.left)
        self.assertIsNone(w.composer);self.assertEqual(w.binding.identity,'b')
        self.assertFalse(w.apply_snapshot('a',{'available':True},revision))
        w.page_layout.until=time.monotonic()-1;w.tick();self.assertTrue(w.visible);self.assertTrue(w.layout_waiting)
        self.assertIsNone(w.composer);self.assertIsNone(w.snapshot)

if __name__=='__main__':unittest.main()
