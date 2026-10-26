import struct
import sys
import unittest
import zlib
import threading
from snapshot_cache import SnapshotCache

import overlay_style as style
from active_chat import Binding


SNAPSHOT = {"available":True,"rounds":3,"requests":28,"turn_requests":28,"latest_tps_estimate":138.3,
            "cache_hit_percent":100,"context_percent_estimate":75,"usage":{"total_tokens":7880000}}


def decode_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG signature")
    offset, packed, dimensions = 8, bytearray(), None
    while offset < len(data):
        size = struct.unpack(">I",data[offset:offset+4])[0]
        kind, value = data[offset+4:offset+8], data[offset+8:offset+8+size]
        crc = struct.unpack(">I",data[offset+8+size:offset+12+size])[0]
        if zlib.crc32(kind+value)&0xffffffff != crc:
            raise ValueError("Invalid PNG checksum")
        if kind == b"IHDR":
            dimensions = struct.unpack(">IIBBBBB",value)
        elif kind == b"IDAT":
            packed.extend(value)
        offset += size+12
    return dimensions, zlib.decompress(packed)


@unittest.skipUnless(sys.platform == "win32", "Built-in GDI+ renderer requires Windows")
class RenderingTests(unittest.TestCase):
    def test_content_width_grows_and_shrinks_without_leaving_fixed_metric_slots(self):
        from product_strip import layout_width,selected_capsule
        from strip_renderer import render
        short={**SNAPSHOT,'visible_metrics':('quota','recent'),'quota_display':{'quota':'25%','recent':'4%'},
               'quota_config':{'capsule_primary':'quota','capsule_secondary':'recent','hours':3}}
        long={**short,'quota_display':{'quota':'100%','recent':'125%'},'quota_config':{**short['quota_config'],'hours':168}}
        for capsule in (False,True):
            for font in (13,15,17):
                for dpi in (1,1.25,1.5,2):
                    with self.subTest(capsule=capsule,font=font,dpi=dpi):
                        a={**short,'capsule':capsule,'font_size':font};b={**long,'capsule':capsule,'font_size':font}
                        self.assertGreater(layout_width(b),layout_width(a)+25)
                        scale=font/15*dpi
                        for snapshot in (a,b,a):
                            width=round(layout_width(snapshot)*scale);_,cells=render(snapshot,width,scale)
                            self.assertEqual([c['key'] for c in cells],['quota','recent'])
                            self.assertAlmostEqual(cells[1]['icon_left']-cells[0]['text_right'],14,delta=.01)
                            self.assertAlmostEqual(width/scale-cells[-1]['text_right'],15 if capsule else 43,delta=.7)
                            self.assertTrue(all(c['text_right']<=c['right']-9 for c in cells))
        one={**short,'capsule':True,'quota_config':{**short['quota_config'],'capsule_secondary':None}}
        two={**short,'capsule':True}
        self.assertLess(layout_width(one),layout_width(two)-40)
        self.assertLess(layout_width(two),195)
    def test_png_baselines_and_columns_across_font_sizes_dpi_and_narrow_panes(self):
        from strip_renderer import render
        from product_strip import layout_width
        normal=round(max(layout_width({**SNAPSHOT,'font_size':font}) for font in (13,15,17)))
        for font_size,dpi,width in ((13,1,normal),(15,1,normal),(17,1,normal),
                                    (15,1.5,normal),(15,2,normal),(15,1,384)):
            scale = font_size/15*dpi
            pixel_width = round(width*scale)
            with self.subTest(font_size=font_size,dpi=dpi,width=width):
                png, layout = render({**SNAPSHOT,"font_size":font_size},pixel_width,scale)
                dimensions, rows = decode_png(png)
                self.assertEqual(dimensions,(pixel_width,round({13:36,15:40,17:44}[font_size]*dpi),8,6,0,0,0))
                self.assertEqual(len(rows),(pixel_width*4+1)*dimensions[1])
                self.assertLess(min(rows[1:]),150)  # readable ink actually exists
                self.assertEqual(len(set(cell["baseline"] for cell in layout)),1)
                for cell in layout:
                    self.assertGreaterEqual(cell["icon_left"]-cell["left"]+1e-6,4)
                    self.assertGreaterEqual(cell["text_left"]-cell["icon_left"]+1e-6,23)
                    self.assertLessEqual(cell["text_right"],cell["right"]-7)
                keys = [cell["key"] for cell in layout]
                self.assertIn("speed",keys)
                self.assertIn("tokens",keys)
                if width == normal:
                    self.assertEqual(keys,list(style.ORDER))

    def test_equal_digit_updates_keep_tabular_alignment_and_longer_values_grow_whole_cells(self):
        from strip_renderer import render
        from product_strip import layout_width
        initial={**SNAPSHOT,'cache_hit_percent':83,'context_percent_estimate':75,'rounds':21,'requests':531}
        changed={**initial,'cache_hit_percent':97,'context_percent_estimate':89,'rounds':42,'requests':973,'latest_tps_estimate':243.9}
        width=round(max(layout_width(initial),layout_width(changed)))
        _,before=render(initial,width);_,after=render(changed,width)
        boundary=lambda cells:[(x['key'],round(x['left'],2),round(x['right'],2)) for x in cells]
        self.assertEqual(boundary(before),boundary(after))
        high={**changed,'usage':{'total_tokens':175800000},'requests':9999}
        _,cells=render(high,round(layout_width(high)))
        self.assertEqual([x['key'] for x in cells],list(style.ORDER))
        self.assertTrue(all(x['text_right']<=x['right']-9 for x in cells))

    def test_missing_values_share_one_tone_across_roles_and_themes(self):
        import theme
        from strip_renderer import Renderer
        def glyph(text,role):
            r=Renderer(120,1)
            try:
                r.text(10,style.Run(text,role))
                return r.png()
            finally:r.close()
        try:
            for seed in (theme.DEFAULT,"#102fd9","#36824b"):
                theme.activate(seed)
                self.assertEqual(glyph("—","speed"),glyph("—","value"))
                self.assertEqual(glyph("28.8","speed"),glyph("28.8","value"))
        finally:theme.activate(theme.DEFAULT)

    def test_window_uses_the_exact_exported_png(self):
        import tkinter as tk
        from overlay import Overlay
        from strip_renderer import render
        window = Overlay.__new__(Overlay)
        window.root = tk.Tk()
        window.root.withdraw()
        try:
            window.tk, window.render_strip = tk, render
            window.canvas = tk.Canvas(window.root)
            window.snapshot, window.scale, window.font_size = SNAPSHOT, 1, 15
            window.visible_metrics = style.ORDER
            window.bound_title = "测试对话"
            window.binding = Binding().pin("test","测试对话")
            window.hovered, window.image_item, window.image = False, None, None
            window.render_error = None
            window.draw(style.WIDTH)
            self.assertIsNone(window.render_error)
            self.assertEqual((window.image.width(),window.image.height()),(style.WIDTH,style.HEIGHT))
            png,_ = render({**SNAPSHOT,"bound_title":window.bound_title},style.WIDTH)
            _,rows = decode_png(png)
            x,y = 90,19
            start = y*(style.WIDTH*4+1)+1+x*4
            self.assertEqual(window.image.get(x,y),tuple(rows[start:start+3]))
            window.hovered = True
            window.draw(style.WIDTH)
            self.assertEqual(len(window.canvas.find_all()),1)
        finally:
            window.root.destroy()

    def test_switch_drops_previous_data_and_rejects_queued_old_snapshot(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from overlay import Overlay
        window=Overlay.__new__(Overlay)
        window.args=SimpleNamespace(thread_id="old")
        window.cache,window.metrics_wake=SnapshotCache(),threading.Event()
        window.bound_title="旧对话"
        window.binding=Binding().pin("old","旧对话")
        window.snapshot=SNAPSHOT
        window.thread_choice,window.follow_choice,window.menu,window.root=Mock(),Mock(),Mock(),Mock()
        window.last_bounds=None
        window.select_thread("new","新对话")
        self.assertIsNone(window.snapshot)
        self.assertFalse(window.apply_snapshot("old",SNAPSHOT,1))
        self.assertIsNone(window.snapshot)
        self.assertTrue(window.apply_snapshot("new",{"available":False},window.binding.revision))

    def test_auto_unknown_clears_previous_metrics(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from overlay import Overlay
        window=Overlay.__new__(Overlay)
        window.args=SimpleNamespace(thread_id="a")
        window.cache,window.metrics_wake=SnapshotCache(),threading.Event()
        window.binding=Binding().follow("A",[{"id":"a","title":"A"}])
        window.bound_title="A"
        window.snapshot=SNAPSHOT
        window.thread_choice,window.follow_choice,window.menu,window.root=Mock(),Mock(),Mock(),Mock()
        window.last_bounds=None
        window.apply_binding(window.binding.follow(None,[],"unavailable"))
        self.assertIsNone(window.snapshot)
        self.assertIsNone(window.args.thread_id)
        self.assertFalse(window.apply_snapshot("a",SNAPSHOT,1))


if __name__ == "__main__":
    unittest.main()
