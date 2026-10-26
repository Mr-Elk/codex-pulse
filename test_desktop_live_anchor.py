import unittest
from types import SimpleNamespace
from overlay_geometry import Rect,DesktopAnchor,place,panel_bounds


class DesktopLiveAnchorTests(unittest.TestCase):
    def test_changing_speed_width_keeps_strip_and_panel_left(self):
        area=Rect(0,0,1920,1040);manual={'center_ratio':.7,'bottom_gap':264};anchor=DesktopAnchor()
        values=[anchor.place(area,width,40,manual=manual) for width in (182,206,189,182,206,182)]
        self.assertEqual(len({r.left for r in values}),1)
        self.assertEqual(len({panel_bounds(area,r,478,672).left for r in values}),1)
        self.assertEqual(manual,{'center_ratio':.7,'bottom_gap':264})

    def test_height_changes_keep_vertical_midpoint_and_left(self):
        area=Rect(0,0,1920,1040);anchor=DesktopAnchor();a=anchor.place(area,182,40);b=anchor.place(area,206,44)
        self.assertEqual(a.left,b.left);self.assertEqual(a.top+a.bottom,b.top+b.bottom)

    def test_user_move_work_area_and_dpi_take_precedence(self):
        anchor=DesktopAnchor();area=Rect(-1920,0,0,1040)
        anchor.place(area,182,40,manual={'center_ratio':.4,'bottom_gap':264})
        moved={'center_ratio':.8,'bottom_gap':100}
        self.assertEqual(anchor.place(area,206,40,manual=moved),place(area,206,40,manual=moved))
        other=Rect(0,0,1280,720)
        self.assertEqual(anchor.place(other,309,60,manual=moved,scale=1.5),place(other,309,60,manual=moved,scale=1.5))

    def test_right_edge_clamps_and_does_not_jump_back_on_shrink(self):
        area=Rect(0,0,600,400);anchor=DesktopAnchor();manual={'center_ratio':.95,'bottom_gap':50}
        a=anchor.place(area,100,40,manual=manual);b=anchor.place(area,200,40,manual=manual);c=anchor.place(area,100,40,manual=manual)
        self.assertLessEqual(b.right,area.right);self.assertEqual(b.left,c.left)

    def test_native_placement_uses_live_anchor(self):
        from overlay import Overlay
        owner=SimpleNamespace(font_size=15,scale=1,display_mode='desktop',desktop_position={'center_ratio':.7,'bottom_gap':264})
        area=Rect(0,0,1920,1040);owner.desired_width=lambda:182
        first=Overlay.anchored_bounds(owner,area);owner.desired_width=lambda:206
        second=Overlay.anchored_bounds(owner,area)
        self.assertEqual(first.left,second.left);self.assertEqual(second.width,206)


if __name__=='__main__':unittest.main()
