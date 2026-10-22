import unittest
from unittest.mock import Mock,patch
from native_foreground import PaintGuard
import test_layering as layering


class ForegroundPaintTests(unittest.TestCase):
    def test_tk_paints_are_consumed_only_after_a_native_frame_exists(self):
        with patch('native_foreground.controls') as controls,patch('native_foreground.user') as user:
            guard=PaintGuard([100,101],lambda:True)
            self.assertEqual(guard.dispatch(100,0x0f,0,0),0)
            self.assertEqual(guard.dispatch(101,0x14,0,0),1)
            user.ValidateRect.assert_called_once_with(100,None)
            controls.DefSubclassProc.assert_not_called()
            guard.ready=lambda:False
            guard.dispatch(100,0x0f,0,0)
            controls.DefSubclassProc.assert_called_once_with(100,0x0f,0,0)
            guard.close()

    def test_mouse_focus_size_and_other_events_still_reach_tk(self):
        with patch('native_foreground.controls') as controls:
            guard=PaintGuard([100],lambda:True)
            for message in (0x200,0x201,0x202,0x203,0x5,0x7,0x8):
                guard.dispatch(100,message,11,22)
            self.assertEqual(controls.DefSubclassProc.call_count,7)
            self.assertEqual(guard.suppressed,0)
            guard.close()

    def test_native_toolbar_does_not_schedule_a_competing_canvas_image_paint(self):
        owner=layering.YieldTests().window()
        owner.surface=Mock();owner.surface.material.available=True
        owner.hovered=False
        owner.render_strip=Mock(return_value=(b'PNG',[]))
        owner.tk=Mock();owner.render_key=None;owner.image_item=None
        from overlay import Overlay
        Overlay.draw(owner,808)
        owner.surface.set_image.assert_called_once_with(b'PNG')
        owner.tk.PhotoImage.assert_not_called()
        owner.canvas.create_image.assert_not_called()
        owner.canvas.itemconfigure.assert_not_called()


if __name__=='__main__':unittest.main()
