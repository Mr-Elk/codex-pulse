import unittest
from unittest.mock import Mock,call
from types import SimpleNamespace
from overlay_geometry import Rect,place
from test_layering import YieldTests


class DisplayPresentationTests(unittest.TestCase):
    def test_open_panel_follows_native_mode_without_changing_expansion(self):
        for compact in (False,True):
            with self.subTest(compact=compact):
                w=YieldTests().window();w.compact=compact
                w.surface=SimpleNamespace(material=SimpleNamespace(hwnd=201))
                w.settings_panel=SimpleNamespace(hwnd=301,closed=False)
                w.metric_tooltip=Mock();w.commit_presentation=Mock();w.save_preferences=Mock()
                w.anchor_desktop_resize=Mock()
                for mode in ('desktop','composer','desktop'):
                    w.win.reset_mock();w.metric_tooltip.reset_mock()
                    w.set_display_mode(mode)
                    native=[c for c in w.win.mock_calls if c.args and c.args[0]==301]
                    expected=[call.set_floating(301,False),call.own_overlay(301,None if mode=='desktop' else w.target['hwnd'])]
                    if mode=='desktop':expected.append(call.set_floating(301,True))
                    self.assertEqual(native,expected)
                    self.assertEqual(w.compact,compact)
                    w.metric_tooltip.hide.assert_called_once_with()

    def test_raising_existing_settings_reveals_hover_again_after_restacking(self):
        w=YieldTests().window();w.passthrough=False
        actions=Mock();w.metric_tooltip=actions.tooltip
        w.settings_panel=SimpleNamespace(window=SimpleNamespace(lift=actions.lift))
        w.context_menu(SimpleNamespace(x_root=10,y_root=10))
        self.assertEqual(actions.mock_calls,[call.tooltip.hide(),call.lift()])

    def test_mode_roundtrips_preserve_expansion_and_chat_identity(self):
        for compact in (False,True):
            for available in (False,True):
                with self.subTest(compact=compact,available=available):
                    w=YieldTests().window();w.compact=compact
                    w.surface=SimpleNamespace(material=SimpleNamespace(hwnd=201))
                    w.commit_presentation=Mock();w.save_preferences=Mock()
                    w.context_ready=lambda:available
                    w.win.work_area.return_value=Rect(0,0,1920,1040)
                    before=(w.binding.identity,list(w.visible_metrics),w.manual)
                    for _ in range(5):
                        for mode in ('desktop','composer'):
                            w.set_display_mode(mode)
                            self.assertEqual(w.is_capsule(),compact)
                            self.assertEqual((w.binding.identity,list(w.visible_metrics),w.manual),before)
                    self.assertEqual(w.commit_presentation.call_count,10)

    def test_expanded_strip_uses_host_space_when_composer_is_narrow(self):
        for scale in (1,1.5,2):
            r=lambda a:Rect(*(round(v*scale) for v in a))
            host=r((100,100,1260,820));composer=r((390,680,758,790))
            saved={'anchor':'composer','center_ratio':.5,'left_ratio':.065,'gap':7}
            full=place(host,round(650*scale),round(40*scale),composer,saved,scale)
            self.assertEqual(full.width,round(650*scale))
            self.assertEqual(full.left,composer.left+round(composer.width*.065))
            pill=place(host,round(190*scale),round(40*scale),composer,saved,scale,capsule=True)
            self.assertEqual(pill.left,full.left)
            self.assertLessEqual(pill.right,composer.right)

    def test_real_host_boundary_still_limits_both_presentations(self):
        host=Rect(100,100,500,700);composer=Rect(300,500,490,650)
        for capsule in (False,True):
            result=place(host,800,40,composer,scale=1,capsule=capsule)
            self.assertGreaterEqual(result.left,host.left)
            self.assertLessEqual(result.right,host.right)
            self.assertEqual(result.bottom,composer.top-7)


if __name__=='__main__':unittest.main()
