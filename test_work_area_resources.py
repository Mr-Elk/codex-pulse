import ctypes
import gc
import unittest
from unittest.mock import patch
import native_windows as native
from overlay_geometry import Rect


class WorkAreaResourceTests(unittest.TestCase):
    def test_repeated_queries_keep_pointer_type_cache_bounded_and_negative_monitor_coordinates(self):
        # ctypes retains every Structure/POINTER pair. A new class per frame
        # leaked even after cyclic GC; this checks that resource boundary.
        before=len(ctypes._pointer_type_cache)
        def fill(monitor,info):
            self.assertEqual(info._obj.size,ctypes.sizeof(info._obj))
            info._obj.work=native.W.RECT(-1920,-100,0,940)
            return True
        with patch.object(native.user32,'MonitorFromWindow',return_value=1),patch.object(native.user32,'GetMonitorInfoW',side_effect=fill):
            for _ in range(2000):self.assertEqual(native.work_area(100),Rect(-1920,-100,0,940))
        gc.collect()
        self.assertLessEqual(len(ctypes._pointer_type_cache)-before,1)

    def test_unavailable_monitor_is_not_replaced_with_fake_geometry(self):
        with patch.object(native.user32,'MonitorFromWindow',return_value=0),patch.object(native.user32,'GetMonitorInfoW') as get:
            self.assertIsNone(native.work_area(100));get.assert_not_called()


if __name__=='__main__':unittest.main()
