from types import SimpleNamespace
from unittest.mock import Mock
import unittest
import test_panel_layout


class MetricSortingTests(unittest.TestCase):
    def event(self,row,dy=0,x=12):
        return SimpleNamespace(x_root=row.winfo_rootx()+x,y_root=row.winfo_rooty()+20+dy)

    def test_native_rows_follow_before_release_and_preferences_commit_only_once(self):
        for scale in (1,1.5,2):
            with self.subTest(scale=scale),test_panel_layout.PanelLayoutTests().panel(scale) as (p,root,_):
                sorter=p.metric_sorter;original=list(p.owner.metric_order);moving=original[0]
                row=sorter.rows[moving];handle=next(w for w in row.winfo_children() if w.cget('cursor')=='fleur')
                save=p.owner.select_metrics=Mock();start=self.event(row);top=row.winfo_rooty()
                sorter.start(moving,handle,start);sorter.move(SimpleNamespace(x_root=start.x_root,y_root=start.y_root+sorter.height*2));root.update()
                self.assertEqual(row.winfo_rooty(),top+sorter.height*2)
                self.assertTrue(sorter.slot.winfo_ismapped());self.assertEqual(int(sorter.slot.place_info()['y']),sorter.height*2)
                self.assertEqual(p.owner.metric_order,original);save.assert_not_called()
                drop=SimpleNamespace(x_root=start.x_root,y_root=start.y_root+sorter.height*2)
                sorter.drop(drop);root.update()
                expected=original[1:3]+[moving]+original[3:]
                self.assertEqual(p.owner.metric_order,expected);save.assert_called_once()
                self.assertFalse(sorter.slot.winfo_ismapped());self.assertIsNone(handle.grab_current())

    def test_escape_outside_and_page_change_cancel_preview(self):
        for reason in ('escape','outside','page'):
            with self.subTest(reason=reason),test_panel_layout.PanelLayoutTests().panel() as (p,root,_):
                sorter=p.metric_sorter;original=list(p.owner.metric_order);key=original[1];row=sorter.rows[key]
                handle=next(w for w in row.winfo_children() if w.cget('cursor')=='fleur');start=self.event(row);p.owner.select_metrics=Mock()
                sorter.start(key,handle,start);sorter.move(SimpleNamespace(x_root=start.x_root,y_root=start.y_root+80));root.update()
                if reason=='escape':sorter.cancel()
                elif reason=='outside':sorter.drop(SimpleNamespace(x_root=sorter.host.winfo_rootx()-100,y_root=start.y_root+80))
                else:p.show_tab('display');root.update()
                self.assertEqual(p.owner.metric_order,original);p.owner.select_metrics.assert_not_called()
                self.assertIsNone(sorter.active);self.assertIsNone(sorter.animation);self.assertIsNone(sorter.scroll_job)

    def test_click_jitter_and_disabled_animation_do_not_change_selection(self):
        with test_panel_layout.PanelLayoutTests().panel() as (p,root,_):
            sorter=p.metric_sorter;key=sorter.order[0];row=sorter.rows[key];handle=next(w for w in row.winfo_children() if w.cget('cursor')=='fleur');start=self.event(row)
            p.owner.select_metrics=Mock();before={k:v.get() for k,v in p.owner.metric_choices.items()}
            sorter.start(key,handle,start);sorter.drop(SimpleNamespace(x_root=start.x_root+1,y_root=start.y_root+1));p.owner.select_metrics.assert_not_called()
            p.owner.animations=False;sorter.start(key,handle,start);sorter.move(SimpleNamespace(x_root=start.x_root,y_root=start.y_root+80));root.update()
            self.assertIsNone(sorter.animation);self.assertEqual({k:v.get() for k,v in p.owner.metric_choices.items()},before);sorter.cancel()

    def test_keyboard_moves_in_both_directions_and_keeps_visual_order(self):
        from product_panel import move_order
        with test_panel_layout.PanelLayoutTests().panel() as (p,root,_):
            original=list(p.owner.metric_order);key=original[0];p.owner.select_metrics=Mock()
            move_order(p,key,1);root.update()
            self.assertEqual(p.owner.metric_order,original[1:2]+[key]+original[2:])
            self.assertEqual(p.metric_sorter.order,p.owner.metric_order)
            move_order(p,key,-1);root.update()
            self.assertEqual(p.owner.metric_order,original)
            self.assertEqual(p.owner.select_metrics.call_count,2)


if __name__=='__main__':unittest.main()
