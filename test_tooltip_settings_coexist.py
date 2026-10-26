import threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from metric_tooltip import MetricTooltip
from overlay_geometry import Rect


class TooltipSettingsCoexistTests(unittest.TestCase):
    def owner(self,panel,menu_open):
        owner=SimpleNamespace(visible=True,last_bounds=Rect(100,100,600,140),menu_open=menu_open,settings_panel=panel,drag=None,stop=threading.Event(),win=Mock(),font_size=15,scale=1,layout=[{'key':'quota','left':40,'right':120}])
        owner.win.cursor_position.return_value=(170,120)
        return owner

    def assert_hover(self,owner):
        tip=MetricTooltip(owner);tip.show=Mock()
        with patch('metric_tooltip.time.monotonic',side_effect=[1,1,1.25]):tip.poll();tip.poll()
        tip.show.assert_called_once_with('quota',Rect(140,100,220,140))

    def test_normal_settings_open_does_not_block_metric_hover(self):
        self.assert_hover(self.owner(SimpleNamespace(closed=False,modal_open=False),True))

    def test_settings_closed_keeps_existing_hover_behavior(self):
        self.assert_hover(self.owner(None,False))

    def test_modal_dropdown_or_unattached_menu_hides_existing_card(self):
        for panel in (SimpleNamespace(closed=False,modal_open=True),None,SimpleNamespace(closed=True,modal_open=False)):
            with self.subTest(panel=panel):
                tip=MetricTooltip(self.owner(panel,True));tip.window=Mock();tip.key='quota';tip.show=Mock();tip.poll()
                tip.window.withdraw.assert_called_once();tip.show.assert_not_called();self.assertIsNone(tip.key)


if __name__=='__main__':unittest.main()
