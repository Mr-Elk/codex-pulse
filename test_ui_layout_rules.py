import unittest,tkinter.font as font
import test_panel_layout as fixture

class UILayoutRulesTests(unittest.TestCase):
    def test_capsule_labels_fields_and_help_fit_at_supported_scales(self):
        for scale in (1,1.25,1.5,2):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale) as (p,root,_):
                p.strip_view='capsule';p.show_tab('strip');root.update()
                rows=p.capsule_rows;selectors=list(p.capsule_selectors.values())
                for row,selector in zip(rows,selectors):
                    label=next(w for w in row.winfo_children() if hasattr(w,'cget') and w.winfo_class()=='Label')
                    label_center=label.winfo_y()+label.winfo_height()/2
                    field_center=selector.winfo_y()+selector.winfo_height()/2
                    self.assertLessEqual(abs(label_center-field_center),1)
                    self.assertLessEqual(label.winfo_x()+label.winfo_width(),selector.winfo_x()-p.px(12))
                self.assertLessEqual(rows[1].winfo_y()-(rows[0].winfo_y()+rows[0].winfo_height()),p.px(12)+1)
                self.assertLessEqual(p.capsule_help.winfo_y()-(rows[1].winfo_y()+rows[1].winfo_height()),p.px(12)+1)
                self.assertLessEqual(p.body.winfo_reqheight(),p.content.winfo_height()+2)

    def test_aggregated_record_values_stay_clear_of_ranges_and_do_not_recreate_on_tick(self):
        from quota_records import aggregate_records
        from datetime import datetime
        now=datetime(2026,10,24,1,30).timestamp()
        records=aggregate_records([{'start':now-60,'at':now-30,'spent':.08,'note':''}],1,now)
        for scale in (1,1.5,2):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale,tab='quota') as (p,root,_):
                page=p.quota_page;page.change_view('usage');page.expanded=True
                if p.quota_job:p.window.after_cancel(p.quota_job);p.quota_job=None
                data={'record':{'rows':records,'bucket_minutes':15}}
                page.update_records(data);root.update()
                frames=[]
                for frame,label,value,detail in page.widgets['record_rows'].values():
                    frames.append(frame)
                    self.assertLessEqual(label.winfo_x()+label.winfo_width(),value.winfo_x())
                    self.assertLessEqual(font.Font(root=label,font=label.cget('font')).measure(label.cget('text')),label.winfo_width())
                    self.assertLessEqual(detail.winfo_y()+detail.winfo_height(),frame.winfo_height())
                    self.assertEqual(value.cget('text'),'<1%')
                page.update_records(data);root.update()
                self.assertEqual(frames,[row[0] for row in page.widgets['record_rows'].values()])

if __name__=='__main__':unittest.main()
