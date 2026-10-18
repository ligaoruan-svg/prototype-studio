"""运行检查没过的那一版留着，AI 在它的基础上修；几段脚本之间重名在提交前就拦下。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, transactions, agent   # noqa: E402
from backend.patcher import PatchError, verify_source   # noqa: E402
from backend.tests.test_keep_work import msg   # noqa: E402


class 修报错(unittest.TestCase):
    PAGE = '<html><head><title>t</title></head><body><h1 id="t">旧</h1></body></html>'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT, agent.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(self.PAGE, encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']

    def tearDown(self):
        storage.DATA_ROOT, agent.chat = self.old
        self.tmp.cleanup()

    def stage_failed(self):
        after = self.PAGE.replace('旧', '新做的一整页')
        token = transactions.stage(self.pid, self.page, self.PAGE, after, '做页面', 'agent')['pending_id']
        with self.assertRaises(PatchError):
            transactions.commit(token, ['Uncaught ReferenceError: x is not defined'], True)
        return token, after

    def test_失败的那一版留着_也存了一份(self):
        token, after = self.stage_failed()
        draft = transactions.failed_draft(token, self.pid, self.page)
        self.assertEqual(draft['after'], after)
        runs = storage.project_dir(self.pid) / 'runs'
        self.assertTrue(list(runs.glob('failed-*.html')))
        self.assertIn('x is not defined', next(runs.glob('failed-*.json')).read_text(encoding='utf-8'))

    def test_页面被别的操作改过就不用那一版(self):
        token, _ = self.stage_failed()
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(self.PAGE.replace('旧', '别人改的'), encoding='utf-8')
        self.assertIsNone(transactions.failed_draft(token, self.pid, self.page))

    def test_在那一版上接着修_不从头做(self):
        token, after = self.stage_failed()
        sent = []
        def chat(api_key, model, messages, tools, **k):
            sent.append([dict(m) for m in messages])
            return msg(('report_result', {'summary': '修好了'}))
        agent.chat = chat
        staged = []
        old_stage = agent.stage
        agent.stage = lambda pid, page, before, aft, *a, **k: staged.append((before, aft)) or {'pending_id': 'y', 'changed': True}
        try:
            out = agent.run_agent(self.pid, self.page, '修报错', 'k', 'm', intent='edit', stream=False,
                                  runtime_feedback='x is not defined', start_source=transactions.failed_draft(token, self.pid, self.page)['after'])
        finally:
            agent.stage = old_stage
        self.assertTrue(out['changed'], '那一版本身就是改动，汇报了就交去检查')
        self.assertEqual(staged[0], (self.PAGE, after), '提交时还是和已保存的页面比')
        self.assertIn('不要从头再做', sent[0][-1]['content'])

    def test_两段脚本重名提交前就拦(self):
        page = '<html><head></head><body><script>const planDevices=[1]</script><script>const planDevices=[2]</script></body></html>'
        issues = verify_source(page)['issues']
        self.assertTrue(any('重复声明：planDevices' in i for i in issues), issues)
        ok = '<html><head></head><body><script>const a=1</script><script>const b=2;function f(){}</script></body></html>'
        self.assertTrue(verify_source(ok)['ok'])


if __name__ == '__main__':
    unittest.main()
