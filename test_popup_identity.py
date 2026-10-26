import os,queue,unittest
from unittest.mock import Mock,patch
from context_probe import PersistentProbe

class PopupIdentityTests(unittest.TestCase):
    def test_live_probe_passes_its_own_parent_identity_to_popup_exclusion(self):
        process=Mock();process.stdout=[]
        with patch('context_probe.subprocess.Popen',return_value=process) as create:
            p=PersistentProbe();p.start(123)
            argv=create.call_args.args[0]
            self.assertEqual(argv[argv.index('-IgnoreProcessId')+1],str(os.getpid()))
            self.assertIn('-Watch',argv)
            self.assertEqual(argv[argv.index('-WindowHandle')+1],'123')
            p.close()
    def test_fallback_probe_uses_the_same_own_process_exclusion(self):
        from overlay import find_context
        with patch('overlay.subprocess.run',return_value=Mock(stdout='null',returncode=0)) as run:
            find_context(456);argv=run.call_args.args[0]
            self.assertEqual(argv[argv.index('-IgnoreProcessId')+1],str(os.getpid()))
    def test_excluded_own_elements_do_not_remove_real_popup_evidence(self):
        p=PersistentProbe();p.process=Mock();p.process.poll.return_value=None;p.hwnd=1;p.inflight=True
        p.responses.put({'composer':{'left':100,'top':500,'right':700,'bottom':600},'chat_status':'ok','chat_title':'A','interaction_open':True,'popup_bounds':{'left':100,'top':300,'right':300,'bottom':500},'ignored_own_elements':2})
        composer,title,status,popup=p.read(1)
        self.assertTrue(popup);self.assertEqual(p.avoid_rect.top,300);self.assertEqual(p.ignored_own_elements,2)
        p.responses.put({'interaction_open':False,'ignored_own_elements':3});p.inflight=True
        self.assertFalse(p.read(1)[3]);self.assertIsNone(p.avoid_rect);self.assertEqual(p.ignored_own_elements,3)
