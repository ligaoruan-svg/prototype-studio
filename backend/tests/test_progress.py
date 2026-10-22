"""按进度停：还在推进就多给几轮；原地打转（改过以后也算）就催、就收尾；整份源码跟着上下文预算走"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent   # noqa: E402

PAGE = '<html><head><title>t</title></head><body>' + ''.join(f'<p id="p{i}">第{i}段</p>' for i in range(40)) + '</body></html>'


def msg(*calls):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [
        {'id': f'c{i}', 'type': 'function', 'function': {'name': n, 'arguments': json.dumps(a, ensure_ascii=False)}}
        for i, (n, a) in enumerate(calls)]}}]}


def edit(i):
    return msg(('apply_operations', {'operations': [{'action': 'set_text', 'selector': f'#p{i}', 'value': f'新{i}'}]}))


READ = msg(('read_source_slice', {'start': 1, 'end': 3}))
REPORT = msg(('report_result', {'summary': '好了', 'annotations': []}))


class 按进度停(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat, self.old_stage = storage.DATA_ROOT, agent.chat, agent.stage
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(PAGE, encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        agent.stage = lambda *a, **k: {'pending_id': 'x'}
        self.sent, self.events = [], []

    def tearDown(self):
        storage.DATA_ROOT, agent.chat, agent.stage = self.old_root, self.old_chat, self.old_stage
        self.tmp.cleanup()

    def script(self, replies, after=REPORT):
        queue = list(replies)
        def chat(api_key, model, messages, tools, **k):
            self.sent.append(json.loads(json.dumps(messages, ensure_ascii=False)))
            return queue.pop(0) if queue else after
        agent.chat = chat

    def run_agent(self, rounds=10, budget=200_000):
        return agent.run_agent(self.pid, self.page, '把这些段落都改了', 'k', 'm', intent='edit', stream=False,
                               max_rounds=rounds, context_budget=budget, on_event=self.events.append)

    def test_一直在改_到上限前多给几轮(self):
        self.script([edit(i) for i in range(14)])
        out = self.run_agent(rounds=10)
        self.assertTrue(out['changed'])
        self.assertEqual(len([t for t in out['tool_log'] if t['tool'] == 'apply_operations' and t['output'].get('ok')]), 14,
                         '还在推进就不在第 10 轮掐断')
        self.assertTrue(any(e.get('id', '').startswith('extend') for e in self.events))
        self.assertEqual(out['report']['summary'], '好了')

    def test_改过一处以后光读也算空转_会被催(self):
        self.script([edit(0)] + [READ] * 6)
        self.run_agent(rounds=20)
        nudges = [m['content'] for s in self.sent for m in s if m.get('role') == 'user' and '没有进展' in str(m.get('content'))]
        self.assertTrue(nudges, '以前改过一处以后，读多少轮都不算空转')

    def test_改过以后原地打转_收尾时改好的保留(self):
        self.script([edit(0)] + [READ] * 12)
        out = self.run_agent(rounds=30)
        self.assertTrue(out['changed'], '改好的那处照样交给检查和保存')
        self.assertLess(len(self.sent), 12, '不会一直读到轮次用完')

    def test_原地打转不多给轮次(self):
        self.script([READ] * 30)
        with self.assertRaises(Exception):
            self.run_agent(rounds=8)
        self.assertFalse(any(e.get('id', '').startswith('extend') for e in self.events))

    def test_整份源码跟着上下文预算走(self):
        big = '<html><head><title>t</title></head><body>' + '<p>' + 'x' * 90_000 + '</p></body></html>'
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(big, encoding='utf-8')
        self.script([], after=REPORT)
        self.run_agent(budget=200_000)
        self.assertIn('完整源码', self.sent[0][-1]['content'], '默认预算 20 万字：10 万字以内整份给')
        self.sent.clear()
        self.run_agent(budget=100_000)
        self.assertNotIn('完整源码', self.sent[0][-1]['content'], '预算小：超过一半就不整份给')


if __name__ == '__main__':
    unittest.main()
