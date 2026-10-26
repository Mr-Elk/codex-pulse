"""Draft ownership and control boundaries in the native approved product flow."""
import copy,unittest,tkinter as tk
from test_panel_layout import PanelLayoutTests
from product_controls import Select,hours_dialog
from quota_service import clean_config

class ProductUITests(unittest.TestCase):
    def test_info_opens_with_its_action_focused_and_enter_closes_only_the_dialog(self):
        from product_controls import info
        with PanelLayoutTests().panel() as (p,root,_):
            info(p,'统计说明','清晰说明');root.update()
            dialog=next(iter(p.dialogs));caption=dialog.focus_get()
            self.assertEqual(caption.cget('text'),'知道了')
            caption.event_generate('<Return>');root.update()
            self.assertFalse(p.dialogs);self.assertTrue(p.window.winfo_exists())
    def test_focused_selector_routes_navigation_to_its_open_menu(self):
        with PanelLayoutTests().panel() as (p,root,_):
            changes=[];s=Select(p,p.body,[('a','一'),('b','二',True),('c','三')],'a',changes.append);s.pack();root.update()
            popup=s.open();s.focus_force();root.update()
            s.event_generate('<End>');root.update()
            self.assertTrue(popup.menu_items[-1].keyboard_focus)
            self.assertFalse(popup.menu_items[0].keyboard_focus)
            s.event_generate('<Return>');root.update()
            self.assertEqual(changes,['c']);self.assertIsNone(s.popup)
    def test_menu_owner_escape_cancels_without_closing_parent_or_changing_value(self):
        with PanelLayoutTests().panel() as (p,root,_):
            changes=[];s=Select(p,p.body,[('a','标准额度'),('b','额外余额',True),('c','重置时间')],'a',changes.append);s.pack();root.update()
            original=p.window.bind('<Escape>')
            popup=s.open();root.update()
            # A key sent to the owner after native activation still belongs to
            # the open menu, and arrow navigation must skip unavailable items.
            popup.menu_items[0].focus_force();p.window.event_generate('<Down>');root.update()
            self.assertEqual(popup.focus_get(),popup.menu_items[1])
            p.window.event_generate('<Escape>');root.update()
            self.assertIsNone(s.popup);self.assertTrue(p.window.winfo_exists())
            self.assertEqual(s.value,'a');self.assertEqual(changes,[])
            self.assertEqual(p.window.bind('<Escape>'),original)
    def test_dropdown_escape_does_not_commit_and_keyboard_choose_commits_once(self):
        with PanelLayoutTests().panel() as (p,root,area):
            p.modal_open=False
            changes=[];s=Select(p,p.body,[('a','标准额度'),('b','额外余额')],'a',changes.append);s.pack();root.update()
            popup=s.open();root.update();self.assertTrue(p.modal_open)
            self.assertGreaterEqual(popup.winfo_x(),area.left);self.assertLessEqual(popup.winfo_x()+popup.winfo_width(),area.right)
            self.assertTrue(popup.bind('<Escape>'));s.cancel();root.update();self.assertEqual(changes,[]);self.assertEqual(s.value,'a')
            popup=s.open();root.update()
            buttons=popup.menu_items
            buttons[1].invoke();root.update();self.assertEqual(changes,['b']);self.assertEqual(s.value,'b');self.assertFalse(p.modal_open)

    def test_custom_hours_draft_validation_cancel_and_seven_day_boundary(self):
        with PanelLayoutTests().panel() as (p,root,_):
            values=[];d=hours_dialog(p,3,values.append);root.update()
            for raw in ('0','169','1.5','-3','abc','１２'):
                d.hours_entry.delete(0,'end');d.hours_entry.insert(0,raw);d.apply_value();root.update()
                self.assertEqual(values,[]);self.assertTrue(d.winfo_exists())
            d.cancel_value();root.update();self.assertEqual(values,[])
            d=hours_dialog(p,3,values.append);root.update();d.hours_entry.delete(0,'end');d.hours_entry.insert(0,'168');d.apply_value();root.update()
            self.assertEqual(values,[168]);self.assertFalse(p.modal_open)

    def test_config_migration_canonicalizes_duplicate_defaults(self):
        config=clean_config({'capsule':'task','capsule_primary':'invalid','capsule_secondary':'tokens'})
        self.assertEqual(config['capsule_primary'],'tokens');self.assertIsNone(config['capsule_secondary'])

if __name__=='__main__':unittest.main()
