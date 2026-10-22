"""AI 改到一半自己真跑页面：后台托界面跑、结果变成短结论、改过没跑就汇报时程序先替它跑"""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent, page_check   # noqa: E402

PAGE = '<html><head><title>t</title></head><body><h1 id="t">旧标题</h1><script>const a=1;</script></body></html>'


def msg(*calls):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [
        {'id': f'c{i}', 'type': 'function', 'function': {'name': n, 'arguments': json.dumps(a, ensure_ascii=False)}}
        for i, (n, a) in enumerate(calls)]}}]}


EDIT = ('apply_operations', {'operations': [{'action': 'set_text', 'selector': '#t', 'value': '新标题'}]})
REPORT = ('report_result', {'summary': '改好了', 'annotations': []})


class 结论要短(unittest.TestCase):
    def test_没回话就说没法跑(self):
        out = page_check.summarize('load', None)
        self.assertFalse(out['ok'])
        self.assertEqual(out['code'], 'unavailable')

    def test_原来就有的报错不算(self):
        out = page_check.summarize('load', {'pages': [{'route': '#a', 'title': '订单', 'errors': ['老错误', '新错误']}], 'baseline': ['老错误']})
        self.assertEqual([e['error'] for e in out['new_errors']], ['新错误'])
        self.assertIn('有问题', out['summary'])

    def test_都正常(self):
        out = page_check.summarize('click', {'pages': [], 'issues': [], 'clicked': 12})
        self.assertEqual(out['clicked'], 12)
        self.assertIn('都正常', out['summary'])

    def test_量出来太多就截(self):
        items = [{'selector': f'.x{i}', 'first': [{'text': 'y' * 24, 'left': i}] * 6} for i in range(8)]
        out = page_check.summarize('measure', {'route': '#a', 'items': items})
        self.assertLessEqual(len(str(out)), 2700)


class 托界面跑(unittest.TestCase):
    def test_发请求等回话(self):
        def emit(event):
            self.assertEqual(event['type'], 'page_check')
            self.assertEqual(page_check.get(event['id'])['html'], '<p>页面</p>')
            threading.Timer(0.1, lambda: page_check.deliver(event['id'], {'pages': [{'route': '', 'errors': []}]})).start()
        result = page_check.request(emit, 'p', 'g', '<p>页面</p>', 'load', {})
        self.assertEqual(result['pages'][0]['route'], '')
        self.assertEqual(page_check.PENDING, {}, '用完就清')

    def test_超时返回空(self):
        self.assertIsNone(page_check.request(lambda e: None, 'p', 'g', 'x', 'load', {}, timeout=0.6))

    def test_停止就不等了(self):
        self.assertIsNone(page_check.request(lambda e: None, 'p', 'g', 'x', 'load', {}, should_stop=lambda: True))


class 循环里真跑(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat, self.old_stage = storage.DATA_ROOT, agent.chat, agent.stage
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(PAGE, encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        agent.stage = lambda *a, **k: {'pending_id': 'x'}
        self.checks, self.events = [], []

    def tearDown(self):
        storage.DATA_ROOT, agent.chat, agent.stage = self.old_root, self.old_chat, self.old_stage
        self.tmp.cleanup()

    def script(self, *replies):
        queue = list(replies)
        def chat(api_key, model, messages, tools, **k):
            return queue.pop(0) if queue else msg(REPORT)
        agent.chat = chat

    def ui(self, *answers):
        """假装界面：收到 page_check 就按顺序回话；记下它被要求跑了什么、跑的是哪一版页面"""
        answers = list(answers)
        def on_event(event):
            self.events.append(event)
            if event.get('type') == 'page_check':
                self.checks.append((event['kind'], event['args'], page_check.get(event['id'])['html']))
                reply = answers.pop(0) if answers else {'pages': [{'route': '', 'errors': []}]}
                threading.Timer(0.05, lambda: page_check.deliver(event['id'], reply)).start()
        return on_event

    def run_agent(self, on_event):
        return agent.run_agent(self.pid, self.page, '把标题改成新标题', 'k', 'm', intent='edit', stream=False, on_event=on_event, live_checks=True)

    def test_改过没跑就汇报_程序先跑_有报错退回去修(self):
        self.script(msg(EDIT, REPORT), msg(('apply_operations', {'operations': [{'action': 'set_text', 'selector': '#t', 'value': '新标题2'}]})), msg(REPORT))
        out = self.run_agent(self.ui({'pages': [{'route': '', 'title': '首页', 'errors': ['x is not defined']}]}))
        self.assertTrue(out['changed'])
        reports = [t for t in out['tool_log'] if t['tool'] == 'report_result']
        self.assertFalse(reports[0]['output']['ok'], '第一次汇报被退回')
        self.assertIn('x is not defined', reports[0]['output']['error'])
        self.assertTrue(reports[-1]['output']['ok'])
        self.assertEqual(len(self.checks), 2, '修完又自动跑了一次')
        self.assertIn('新标题', self.checks[0][2], '跑的是改到一半、还没保存的那一版')

    def test_自己跑过就不再替它跑(self):
        self.script(msg(EDIT), msg(('check_page', {'click': True})), msg(REPORT))
        out = self.run_agent(self.ui({'pages': [], 'issues': [], 'clicked': 5}))
        check = next(t for t in out['tool_log'] if t['tool'] == 'check_page')['output']
        self.assertEqual(check['clicked'], 5)
        self.assertEqual([c[0] for c in self.checks], ['click'])

    def test_量一下(self):
        self.script(msg(('measure_page', {'route': '#bill', 'selectors': ['.ops a']})), msg(REPORT))
        reply = {'route': '#bill', 'items': [{'selector': '.ops a', 'count': 4, 'differ': {'left': 12}}]}
        out = self.run_agent(self.ui(reply))
        measured = next(t for t in out['tool_log'] if t['tool'] == 'measure_page')['output']
        self.assertEqual(measured['items'][0]['differ']['left'], 12)
        self.assertEqual(self.checks[0][1], {'route': '#bill', 'selectors': ['.ops a']})

    def test_最多跑四次(self):
        calls = [msg(('check_page', {'routes': [f'#p{i}']})) for i in range(5)]
        self.script(*calls, msg(REPORT))
        out = self.run_agent(self.ui())
        outs = [t['output'] for t in out['tool_log'] if t['tool'] == 'check_page']
        self.assertTrue(all(o['ok'] for o in outs[:4]))
        self.assertFalse(outs[4]['ok'])

    def test_没有界面就如实说_不拦汇报(self):
        self.script(msg(EDIT), msg(('check_page', {})), msg(REPORT))
        out = agent.run_agent(self.pid, self.page, '把标题改成新标题', 'k', 'm', intent='edit', stream=False)
        check = next(t for t in out['tool_log'] if t['tool'] == 'check_page')['output']
        self.assertEqual(check['code'], 'unavailable')
        self.assertTrue(out['changed'])


if __name__ == '__main__':
    unittest.main()
