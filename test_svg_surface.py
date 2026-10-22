import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from test_strip_renderer import SNAPSHOT, decode_png
from strip_renderer import render
from svg_art import render_asset
import overlay_style as style


class VectorSurfaceTests(unittest.TestCase):
    def test_icon_stroke_coverage_scales_with_dpi_instead_of_becoming_a_hairline(self):
        for name in ('speed','tokens','cache','context','rounds'):
            coverage=[]
            for scale in (1,2):
                size=24*scale
                _,rows=decode_png(render_asset(name+'.svg',size,size,scale))
                coverage.append(sum(rows[y*(size*4+1)+1+x*4+3] for y in range(size) for x in range(size))/255)
            self.assertGreater(coverage[0],65,name)
            self.assertAlmostEqual(coverage[1]/coverage[0],4,delta=.4,msg=name)

    def test_independent_move_commands_do_not_draw_a_diagonal_connector(self):
        root=ET.fromstring('<svg viewBox="0 0 24 24"><path d="M 2 3 L 8 3 M 16 21 L 22 21" fill="none" stroke="#72799c" stroke-width="2"/></svg>')
        with patch('svg_art.asset',return_value=root):
            _,rows=decode_png(render_asset.__wrapped__('subpath-fixture.svg',24,24))
        alpha=lambda x,y:rows[y*(24*4+1)+1+x*4+3]
        self.assertGreater(alpha(5,3),200)
        self.assertGreater(alpha(19,21),200)
        self.assertEqual(alpha(12,12),0)

    def test_flat_and_round_line_caps_preserve_the_svg_endpoint(self):
        coverage={}
        for cap in ('butt','round'):
            root=ET.fromstring(f'<svg viewBox="0 0 24 24"><path d="M 6 12 L 18 12" fill="none" stroke="#72799c" stroke-width="4" stroke-linecap="{cap}"/></svg>')
            with patch('svg_art.asset',return_value=root):
                _,rows=decode_png(render_asset.__wrapped__('cap-fixture.svg',24,24))
            coverage[cap]=rows[12*(24*4+1)+1+5*4+3]
        self.assertLess(coverage['butt'],30)
        self.assertGreater(coverage['round'],200)

    def test_curved_exterior_has_transparent_corners_and_antialiased_boundary_at_each_dpi(self):
        for scale in (13/15,1,1.25,1.5,2):
            width=round(style.WIDTH*scale)
            png,_=render(SNAPSHOT,width,scale)
            dimensions,rows=decode_png(png)
            height=dimensions[1];stride=width*4+1
            alpha=lambda x,y:rows[y*stride+1+x*4+3]
            self.assertEqual([alpha(x,y) for x,y in ((0,0),(width-1,0),(0,height-1),(width-1,height-1))],[0]*4)
            edge=[alpha(x,y) for y in range(height) for x in range(round(8*scale))]
            self.assertTrue(any(0<a<240 for a in edge))
            self.assertGreater(alpha(width//2,height//2),220)

    def test_generation_frames_keep_bounds_and_the_rest_of_the_strip_unchanged(self):
        previous=None
        for phase in range(3):
            png,layout=render(dict(SNAPSHOT,request_pending=True,activity_phase=phase),style.WIDTH)
            dimensions,rows=decode_png(png)
            signature=[(cell['key'],cell['left'],cell['right']) for cell in layout]
            start=round(layout[0]['right'])+2
            right=b''.join(rows[y*(style.WIDTH*4+1)+1+start*4:(y+1)*(style.WIDTH*4+1)] for y in range(dimensions[1]))
            if previous:
                self.assertEqual(signature,previous[0]);self.assertEqual(right,previous[1])
            previous=signature,right

    def test_svg_controls_resize_without_opaque_rectangular_wings(self):
        for scale in (1,1.25,1.5,2):
            for state in ('on','off'):
                w,h=round(44*scale),round(26*scale)
                dimensions,rows=decode_png(render_asset('toggle-'+state+'.svg',w,h,scale))
                self.assertEqual(dimensions[:2],(w,h))
                self.assertEqual(rows[4],0)


if __name__=='__main__':unittest.main()
