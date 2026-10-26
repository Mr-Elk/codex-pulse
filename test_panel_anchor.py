import unittest
from unittest.mock import Mock
from overlay_geometry import Rect,place,remember_capsule,panel_bounds
import test_panel_layout as fixture

class PanelAnchorTests(unittest.TestCase):
    def test_logo_round_trip_keeps_left_and_center_when_input_height_changes(self):
        for scale in (1,1.25,1.5,2):
            area=Rect(0,0,round(1600*scale),round(1100*scale))
            for top,width in ((900,800),(750,800),(750,527)):
                composer=Rect(round(300*scale),round(top*scale),round((300+width)*scale),round(1010*scale))
                capsule=place(area,round(200*scale),round(40*scale),composer,scale=scale,capsule=True)
                saved=remember_capsule(area,capsule,None,scale,composer)
                expanded=place(area,round(650*scale),round(40*scale),composer,saved,scale)
                restored=place(area,round(200*scale),round(40*scale),composer,saved,scale,True)
                self.assertEqual(capsule,restored)
                self.assertEqual(expanded.left,capsule.left)
                self.assertEqual(expanded.top,capsule.top)
                self.assertLessEqual(expanded.right,area.right)
                self.assertLessEqual(restored.right,composer.right)

    def test_panel_keeps_shared_edge_and_gap_unless_screen_boundary_requires_clamping(self):
        for scale in (1,1.5,2):
            area=Rect(-round(1600*scale),0,0,round(1100*scale))
            anchor=Rect(-round(1200*scale),round(900*scale),-round(1000*scale),round(940*scale))
            panel=panel_bounds(area,anchor,round(478*scale),round(672*scale),scale)
            self.assertEqual(panel.left,anchor.left)
            self.assertEqual(panel.bottom,anchor.top-round(10*scale))
            high=Rect(anchor.left,0,anchor.right,round(40*scale))
            self.assertEqual(panel_bounds(area,high,panel.width,panel.height,scale).top,high.bottom+round(10*scale))
            raised=Rect(anchor.left,round(650*scale),anchor.right,round(690*scale))
            smaller=panel_bounds(area,raised,panel.width,panel.height,scale)
            self.assertEqual(smaller.bottom,raised.top-round(10*scale))
            self.assertLess(smaller.height,panel.height)
            short=panel_bounds(Rect(0,0,640,520),Rect(620,470,640,510),478,672)
            self.assertGreaterEqual(short.left,0);self.assertLessEqual(short.right,640)
            self.assertGreaterEqual(short.top,0);self.assertLessEqual(short.bottom,520)

    def test_account_icon_mouse_keyboard_and_disabled_states_and_retained_panel(self):
        with fixture.PanelLayoutTests().panel(tab='quota') as (p,root,_):
            service=Mock();p.owner.quota_service=service
            button=p.quota_page.widgets['refresh_button'];root.update()
            self.assertEqual(button.cget('text'),'刷新账户数据')
            self.assertEqual((button.winfo_width(),button.winfo_height()),(32,32))
            face=button.normal_caption
            face.event_generate('<ButtonPress-1>',x=16,y=16);face.event_generate('<ButtonRelease-1>',x=16,y=16);root.update()
            self.assertEqual(service.refresh.call_count,1)
            button.configure(state='disabled');root.update();button.inactive_caption.event_generate('<ButtonPress-1>',x=16,y=16);button.inactive_caption.event_generate('<ButtonRelease-1>',x=16,y=16)
            self.assertEqual(service.refresh.call_count,1)
            button.configure(state='normal');button.focus_force();root.update();button.normal_caption.event_generate('<Return>');root.update()
            self.assertEqual(service.refresh.call_count,2)
            window=p.window.winfo_id();p.owner.last_bounds=Rect(320,880,600,920);p.follow_anchor();root.update()
            self.assertEqual(p.bounds.left,320);self.assertEqual(p.bounds.bottom,870)
            self.assertEqual(p.window.winfo_id(),window)
            self.assertEqual(p.window.winfo_height(),672)

if __name__=='__main__':unittest.main()
