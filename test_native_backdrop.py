import unittest
from unittest.mock import Mock,patch
from native_backdrop import Backdrop
from overlay_geometry import Rect


class BackdropTests(unittest.TestCase):
    def backdrop(self):
        obj=Backdrop.__new__(Backdrop)
        obj.hwnd=200;obj.available=True;obj.visible=False;obj.last_rect=None;obj.size=None;obj.reason=None
        obj.instance=42;obj.library=Mock();obj.library.pulse_blur_resize.return_value=0
        obj.shows=obj.hides=obj.moves=0
        return obj

    def test_content_redraws_do_not_move_or_toggle_the_blur_host(self):
        obj=self.backdrop();rect=Rect(100,200,908,256)
        with patch('native_backdrop.user') as user,patch('native_backdrop.win.hide') as hide:
            user.SetWindowPos.return_value=True
            for _ in range(200):obj.place(100,rect,True)
            self.assertEqual(user.SetWindowPos.call_count,1)
            self.assertEqual((obj.shows,obj.hides,obj.moves),(1,0,1));hide.assert_not_called()

    def test_drag_positions_preserve_a_visible_round_blur_host(self):
        obj=self.backdrop()
        with patch('native_backdrop.user') as user,patch('native_backdrop.win.hide') as hide:
            user.SetWindowPos.return_value=True
            for x in range(100,130):obj.place(100,Rect(x,200,x+808,256),True)
            self.assertEqual((obj.shows,obj.hides),(1,0));hide.assert_not_called()
            self.assertEqual(obj.library.pulse_blur_resize.call_count,1)

    def test_failed_round_clip_falls_back_without_showing_a_rectangle(self):
        obj=self.backdrop()
        with patch('native_backdrop.user') as user:
            obj.library.pulse_blur_resize.return_value=-1
            obj.place(100,Rect(100,200,908,256),True)
            self.assertFalse(obj.available);self.assertFalse(obj.visible)
            self.assertEqual(obj.reason,'rounded_clip_unavailable');user.SetWindowPos.assert_not_called()


if __name__=='__main__':unittest.main()
