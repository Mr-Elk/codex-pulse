"""Color axes, literal swatches and fractional-DPI edge quality."""
import tkinter as tk
import unittest

from color_editor import field_png,hex_hsv,hsv_hex
from settings_panel import ThemeButton
from test_strip_renderer import decode_png
from test_theme_and_panel import pixel
import theme


class ColorRenderingTests(unittest.TestCase):
    def tearDown(self):
        theme.activate(theme.DEFAULT)

    def test_color_fields_keep_literal_color_axes_across_themes_and_dpi(self):
        for scale in (1,1.25,1.5,2):
            w,h=round(360*scale),round(126*scale)
            theme.activate(theme.DEFAULT)
            original=field_png(w,h,scale,0,.5,.5,"sv")
            red=pixel(original,round(346*scale),round(14*scale))
            white=pixel(original,round(14*scale),round(14*scale))
            black=pixel(original,round(14*scale),round(112*scale))
            self.assertGreater(red[0],220);self.assertLess(red[1],25)
            self.assertGreater(min(white[:3]),210)
            self.assertLess(max(black[:3]),25)
            for seed in ("#36824b","#c34c86","#3f78db"):
                theme.activate(seed)
                self.assertEqual(field_png(w,h,scale,0,.5,.5,"sv"),original)
        for seed in ("#000000","#ffffff","#8b57f1","#2478b2"):
            self.assertEqual(hsv_hex(*hex_hsv(seed)),seed)

    def test_seed_dot_has_antialiased_edge_and_retains_literal_seed_at_fractional_dpi(self):
        root=tk.Tk();root.withdraw()
        try:
            for scale in (1,1.25,1.5,2):
                theme.activate("#36824b")
                button=ThemeButton(root,"Purple","#8b57f1",lambda:None,scale,"#faf9fd")
                button.place(x=0,y=0,width=round(88*scale),height=round(36*scale))
                root.update_idletasks();button.redraw()
                seed=(139,87,241)
                self.assertEqual(pixel(button.png,round(15*scale),round(18*scale))[:3],seed)
                edge=[pixel(button.png,x,y)[:3] for x in range(round(10*scale),round(20*scale))
                      for y in range(round(13*scale),round(23*scale))]
                self.assertTrue(any(p!=seed and p!=(255,255,255) and all(a<=b<=255 for a,b in zip(seed,p)) for p in edge))
                button.destroy()
        finally:
            root.destroy()


if __name__=="__main__":unittest.main()
