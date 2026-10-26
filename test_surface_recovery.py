"""The text/icon layer must recover independently of data and geometry changes."""
import unittest
from unittest.mock import Mock,patch
from native_surface import Surface
from native_backdrop import Backdrop
from overlay_geometry import Rect
import test_layering as layering
from types import SimpleNamespace


class SurfaceRecoveryTests(unittest.TestCase):
    def surface(self):
        surface=Surface.__new__(Surface)
        surface.hwnd=100;surface.dc=1;surface.size=(808,56)
        surface.shown=True;surface.last_frame=(Rect(0,0,808,56),255)
        surface.material=Mock();surface.last_upload=10
        surface.last_repair=10
        surface.uploads=0;surface.repairs=0;surface.last_error=None
        return surface

    def test_unchanged_pixels_are_recommitted_periodically_without_hiding(self):
        surface=self.surface()
        with patch('native_surface.user') as user,patch('native_surface.time.monotonic',return_value=11.1):
            user.IsWindowVisible.return_value=True;user.UpdateLayeredWindow.return_value=True
            surface.present(Rect(0,0,808,56))
            user.UpdateLayeredWindow.assert_called_once()
            user.ShowWindow.assert_not_called()
            self.assertEqual(surface.repairs,1)
            surface.material.place.assert_called_once_with(100,Rect(0,0,808,56),True,force=True)

    def test_hidden_foreground_is_restored_even_when_cached_frame_is_identical(self):
        surface=self.surface()
        with patch('native_surface.user') as user,patch('native_surface.time.monotonic',return_value=10.1):
            user.IsWindowVisible.return_value=False;user.UpdateLayeredWindow.return_value=True
            surface.present(Rect(0,0,808,56))
            user.UpdateLayeredWindow.assert_called_once()
            user.ShowWindow.assert_called_once_with(100,4)

    def test_fast_stationary_refreshes_still_reuse_the_uploaded_pixels(self):
        surface=self.surface()
        with patch('native_surface.user') as user,patch('native_surface.time.monotonic',return_value=10.1):
            user.IsWindowVisible.return_value=True
            for _ in range(100):surface.present(Rect(0,0,808,56))
            user.UpdateLayeredWindow.assert_not_called()

    def test_settings_open_recommits_existing_content_after_tk_finishes_its_paint(self):
        owner=layering.YieldTests().window();owner.passthrough=False
        owner.surface=Mock()
        with patch('settings_panel.SettingsPanel'):
            owner.context_menu(SimpleNamespace(x_root=600,y_root=700))
        owner.root.after_idle.assert_called_once_with(owner.refresh_surface)
        owner.refresh_surface()
        owner.surface.invalidate.assert_called_once()
        owner.surface.present.assert_called_once_with(owner.last_bounds,owner.opacity)
        owner.win.hide.assert_not_called()

    def test_upload_failure_keeps_the_shell_and_retries_the_next_frame(self):
        surface=self.surface()
        with patch('native_surface.user') as user,patch('native_surface.time.monotonic',return_value=11.1):
            user.IsWindowVisible.return_value=True
            user.UpdateLayeredWindow.side_effect=[False,True]
            surface.present(Rect(0,0,808,56))
            self.assertIsNotNone(surface.last_error)
            surface.present(Rect(0,0,808,56))
            self.assertIsNone(surface.last_error)
            self.assertEqual(user.UpdateLayeredWindow.call_count,2)
            user.ShowWindow.assert_not_called()

    def test_backdrop_repair_reorders_existing_layer_without_hiding_or_resizing(self):
        backdrop=Backdrop.__new__(Backdrop)
        backdrop.hwnd=200;backdrop.available=True;backdrop.visible=True
        rect=Rect(0,0,808,56);backdrop.last_rect=rect;backdrop.size=(792,40)
        backdrop.instance=1;backdrop.library=Mock();backdrop.moves=backdrop.shows=backdrop.hides=0
        with patch('native_backdrop.user') as user,patch('native_backdrop.win.hide') as hide:
            user.SetWindowPos.return_value=True
            backdrop.place(100,rect,True,force=True)
            user.SetWindowPos.assert_called_once()
            backdrop.library.pulse_blur_resize.assert_not_called()
            hide.assert_not_called()


if __name__=='__main__':unittest.main()
