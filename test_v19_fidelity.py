"""User-visible continuity and geometry measured from the approved v19 DOM.

These checks verify geometry and widget lifetime, not screenshot equivalence.
Reference: v19 structure plus UI_RULES.html spacing revision of 2026-10-24.
"""
import copy,time,unittest
from unittest.mock import Mock,patch
import tkinter as tk
import test_panel_layout as fixture
from quota_model import normalize
from quota_service import clean_config
from product_panel import configure,toggle_theme,reorder

class FidelityTests(unittest.TestCase):
    def point(self,p,w):return (round((w.winfo_rootx()-p.window.winfo_rootx())/p.scale),round((w.winfo_rooty()-p.window.winfo_rooty())/p.scale))
    def find(self,p,value):
        def walk(w):
            try:
                if w.winfo_ismapped() and str(w.cget('text'))==value:return w
            except tk.TclError:pass
            for c in w.winfo_children():
                found=walk(c)
                if found is not None:return found
        found=walk(p.body);self.assertIsNotNone(found,value);return found
    def seed(self,p):
        now=time.time();p.owner.quota_snapshot=normalize({'account_id':'layout-fixture','limits':{'rateLimits':{
            'primary':{'usedPercent':70,'windowDurationMins':300,'resetsAt':now+5040},
            'secondary':{'usedPercent':32,'windowDurationMins':10080,'resetsAt':now+194400},
            'credits':{'hasCredits':True,'balance':'320','unlimited':False}},
            'rateLimitResetCredits':{'availableCount':2,'credits':[{'status':'available','expiresAt':now+3600},{'status':'available','expiresAt':now+864000}]}}},now)
        p.owner.quota_preferences=clean_config({'window':'secondary','hours':24});p.refresh()
    def test_seven_pages_share_gutters_and_recorded_spacing_rules(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            self.seed(p)
            for view,checks in [('metrics',{'统计条':(21,138),'Token':(123,244)}),
                    ('capsule',{'主要数据':(21,216),'补充数据':(21,262)}),
                    ('source',{'统计会话':(21,211),'账户用量范围':(21,414),'额度窗口':(21,455)})]:
                p.strip_view=view;p.show_tab('strip');root.update()
                self.assertEqual(self.point(p,p.body),(21,138));self.assertEqual(p.body.winfo_width(),419)
                for text,point in checks.items():self.assertEqual(self.point(p,self.find(p,text)),point)
            p.show_tab('display');root.update()
            for text,point in {'显示统计条':(21,270),'主题颜色':(21,320),'平滑过渡':(21,424),'点击穿透':(21,484)}.items():self.assertEqual(self.point(p,self.find(p,text)),point)
            p.show_tab('quota');root.update()
            for text,point in {'账户资源':(21,138),'标准额度':(21,238),'额外余额':(21,490),'重置卡':(72,573)}.items():self.assertEqual(self.point(p,self.find(p,text)),point)
            p.quota_page.change_view('usage');root.update();self.assertEqual(self.point(p,self.find(p,'最近用量')),(21,143));self.assertEqual(self.point(p,self.find(p,'额度数据')),(38,407))
            p.quota_page.change_view('credits');root.update();self.assertEqual(self.point(p,self.find(p,'返回账户')),(376,146))
    def test_filters_refresh_and_disclosures_retain_the_existing_page_and_controls(self):
        with fixture.PanelLayoutTests().panel(tab='quota') as (p,root,_):
            self.seed(p);page=p.quota_page;page.change_view('usage');root.update()
            body=page.body;selector=page.widgets['hours'];reading=page.widgets['usage'];back=page.widgets['back'];original=copy.deepcopy(p.owner.quota_preferences)
            for hours in (3,17,24,168,1):
                page.change_analysis('hours',hours);page.toggle_records();page.toggle_records();page.refresh();root.update()
                self.assertIs(page.body,body);self.assertIs(page.widgets['hours'],selector);self.assertIs(page.widgets['usage'],reading);self.assertIs(page.widgets['back'],back)
            self.assertEqual(p.owner.quota_preferences,original)
            page.change_view('overview');root.update();overview=page.body;card=page.widgets['cards']['primary']['surface']
            for percent in (31,32,33):p.owner.quota_snapshot['groups'][0]['windows'][0]['remaining']=percent;page.refresh();root.update()
            self.assertIs(page.body,overview);self.assertIs(page.widgets['cards']['primary']['surface'],card)
            page.change_view('usage');root.update();self.assertIs(page.body,body)
    def test_available_quota_windows_fill_the_row_when_source_changes(self):
        for scale in (1,1.5):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale=scale,tab='quota') as (p,root,_):
                self.seed(p);page=p.quota_page;group=p.owner.quota_snapshot['groups'][0]
                both=copy.deepcopy(group['windows']);retained=None
                for windows in (both,[both[1]],both,[both[0]],both):
                    group['windows']=copy.deepcopy(windows);page.refresh();root.update()
                    host=page.widgets['windows'];cards=page.widgets['cards']
                    self.assertEqual(set(cards),{item['role'] for item in windows})
                    if len(windows)==1:
                        card=cards[windows[0]['role']]['surface']
                        self.assertEqual(card.winfo_x(),0)
                        self.assertLessEqual(abs(card.winfo_width()-host.winfo_width()),1)
                        retained=(windows[0]['role'],card)
                    else:
                        left,right=[cards[item['role']]['surface'] for item in windows]
                        self.assertEqual(left.winfo_x(),0)
                        self.assertLessEqual(abs(right.winfo_x()+right.winfo_width()-host.winfo_width()),1)
                        self.assertLessEqual(abs(left.winfo_width()-right.winfo_width()),1)
                        self.assertAlmostEqual((right.winfo_x()-left.winfo_width())/scale,12,delta=1)
                        if retained:self.assertIs(cards[retained[0]]['surface'],retained[1])
    def test_tab_return_capsule_and_theme_changes_do_not_destroy_pages_or_drafts(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            metrics=p.body;row=dict(p.metric_rows)['tokens'];reorder(p,'tokens','credits');root.update();self.assertIs(dict(p.metric_rows)['tokens'],row)
            p.strip_view='capsule';p.show_tab('strip');root.update();capsule=p.body;primary=p.capsule_selectors['capsule_primary']
            configure(p,'capsule_primary','tokens');root.update();self.assertIs(p.body,capsule);self.assertIs(p.capsule_selectors['capsule_primary'],primary)
            p.show_tab('display');root.update();display=p.body;editor=p.color_editor;editor.value.set('#168578')
            for _ in range(4):toggle_theme(p);p.refresh();root.update()
            self.assertIs(p.body,display);self.assertIs(p.color_editor,editor);self.assertEqual(editor.value.get(),'#168578')
            p.strip_view='metrics';p.show_tab('strip');root.update();self.assertIs(p.body,metrics)
    def test_partial_local_history_and_stale_account_both_fit_without_clipping(self):
        with fixture.PanelLayoutTests().panel(tab='quota') as (p,root,_):
            self.seed(p);state=p.owner.quota_snapshot;state['status']='stale';state['observed_at']=time.time()-600
            window=state['groups'][0]['windows'][1]
            state['recent']={'spent':3.9,'sample_count':4,'partial':True,'last_at':time.time()-600,'rows':[],
                'scope':{'account':state['account_key'],'window':window['key'],'basis':window['basis'],'hours':24}}
            page=p.quota_page;page.change_view('usage');root.update();w=page.widgets
            self.assertIn('记录未覆盖全时段',w['local'].cget('text'));self.assertIn('已过期',w['account'].cget('text'))
            self.assertIn('未记录的时段不计入',w['notice'].cget('text'));self.assertIn('额度数据已过期',w['notice'].cget('text'))
            self.assertLessEqual(w['notice'].winfo_y()+w['notice'].winfo_height(),w['card'].winfo_height()-p.px(16))
    def test_hover_is_anchored_to_the_active_metric_instead_of_the_whole_strip(self):
        from metric_tooltip import MetricTooltip
        from overlay_geometry import Rect
        from types import SimpleNamespace
        o=SimpleNamespace(visible=True,last_bounds=Rect(100,100,600,140),menu_open=False,drag=None,stop=Mock(),win=Mock(),font_size=15,scale=1,layout=[{'key':'tokens','left':40,'right':120},{'key':'quota','left':300,'right':380}])
        o.stop.is_set.return_value=False;o.win.cursor_position.return_value=(450,120)
        tip=MetricTooltip(o);tip.show=Mock()
        with patch('metric_tooltip.time.monotonic',side_effect=[1,1,1.2]):tip.poll();tip.poll()
        tip.show.assert_called_once_with('quota',Rect(400,100,480,140))

if __name__=='__main__':unittest.main()
