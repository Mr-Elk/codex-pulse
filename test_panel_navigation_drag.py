"""Regressions found in the real dropdown and attached strip interaction."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import test_panel_layout as fixture
import test_quick_interactions as interactions
from product_panel import strip_view
from settings_panel import SettingsPanel

class PanelNavigationDragTests(unittest.TestCase):
    def test_actual_menu_roundtrips_keep_selected_label_and_retained_content_together(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            bodies={};selectors={}
            titles={'metrics':'指标与顺序','capsule':'收起状态','source':'统计对象与范围'}
            for view in ('capsule','source','metrics','source','capsule','metrics')*2:
                previous=p.active_page[1];outgoing=p.view_selector
                outgoing.open();root.update()
                button=next(b for b in outgoing.popup.menu_items if b.caption.cget('text')==titles[view])
                button.invoke();root.update()
                self.assertEqual(outgoing.value,previous)
                self.assertEqual((p.active_page,p.strip_view),(('strip',view),view))
                self.assertEqual(p.view_selector.value,view)
                self.assertEqual(p.view_selector.label.cget('text'),titles[view])
                self.assertEqual(p.content.itemcget(p.body_item,'window'),str(p.body))
                if view in bodies:
                    self.assertIs(p.body,bodies[view]);self.assertIs(p.view_selector,selectors[view])
                bodies[view],selectors[view]=p.body,p.view_selector
            self.assertEqual(len(p.page_cache),3)
            p.show_tab('display');root.update();p.show_tab('strip');root.update()
            self.assertEqual((p.view_selector.value,p.strip_view),('metrics','metrics'))
    def test_staging_never_paints_destination_label_on_outgoing_content(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            outgoing=p.view_selector;original=p.build_strip;observed=[]
            def build():
                observed.append(outgoing.label.cget('text'));original()
            p.build_strip=build
            outgoing.set('source');strip_view(p,'source');root.update()
            self.assertEqual(observed,['指标与顺序'])
    def test_drag_moves_panel_on_every_real_motion_in_both_modes_and_scales(self):
        helper=interactions.QuickInteractionTests()
        for mode in ('desktop','composer'):
            for scale in (1,1.5,2):
                owner=helper.owner(mode,False,scale);panel=SimpleNamespace(closed=False,follow_anchor=Mock())
                owner.settings_panel=panel;event=helper.press(owner)
                for dx,dy in ((30,20),(70,-20),(90,10)):
                    event.x_root=owner.drag_origin[0]+round(dx*scale);event.y_root=owner.drag_origin[1]+round(dy*scale)
                    owner.drag_move(event)
                    self.assertEqual(owner.last_bounds.left,event.x_root-owner.drag[0])
                    self.assertEqual(panel.follow_anchor.call_count,((30,20),(70,-20),(90,10)).index((dx,dy))+1)
                owner.drag_end(event)
                self.assertFalse(owner.compact)
    def test_own_strip_drag_defers_focus_dismissal_until_release(self):
        panel=SimpleNamespace(closed=False,owner=SimpleNamespace(drag=(10,20)),focus_check=None,modal_open=False,window=Mock(),close=Mock())
        panel.window.focus_displayof.return_value=None
        panel.close_if_outside=lambda:SettingsPanel.close_if_outside(panel)
        panel.close_if_outside();panel.close.assert_not_called();panel.window.after.assert_called_once()
        panel.owner.drag=None;panel.close_if_outside();panel.close.assert_called_once()

if __name__=='__main__':unittest.main()
