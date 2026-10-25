"""大任务一步一步做：截断先放宽上限再试；做完一步 finish_step，对话长了就带着现在的页面重开下一步"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent   # noqa: E402
from backend.deepseek_client import DeepSeekError   # noqa: E402

PAGE = '<html><head><title>t</title></head><body><h1 id="t">旧标题</h1><p id="p">段落</p></body></html>'
CUT = {'choices': [{'finish_reason': 'length', 'message': {'content': ''}}]}


def msg(*calls):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [
        {'id': f'c{i}', 'type': 'function', 'function': {'name': n, 'arguments': json.dumps(a, ensure_ascii=False)}}
        for i, (n, a) in enumerate(calls)]}}]}


def edit(sel, text):
    return ('apply_operations', {'operations': [{'action': 'set_text', 'selector': sel, 'value': text}]})


PLAN = ('update_plan', {'steps': [{'title': '改标题'}, {'title': '改段落'}, {'title': '收尾'}]})
REPORT = ('report_result', {'summary': '好了', 'annotations': []})


class 一步一步(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat, self.old_stage = storage.DATA_ROOT, agent.chat, agent.stage
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(PAGE, encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        agent.stage = lambda *a, **k: {'pending_id': 'x'}
        self.sent, self.limits, self.events = [], [], []

    def tearDown(self):
        storage.DATA_ROOT, agent.chat, agent.stage = self.old_root, self.old_chat, self.old_stage
        self.tmp.cleanup()

    def script(self, *replies):
        queue = list(replies)
        def chat(api_key, model, messages, tools, **k):
            self.sent.append(json.loads(json.dumps(messages, ensure_ascii=False)))
            self.limits.append(k.get('max_tokens'))
            reply = queue.pop(0) if queue else msg(REPORT)
            if isinstance(reply, Exception):
                raise reply
            return reply
        agent.chat = chat

    def run_agent(self, budget=200_000, max_tokens=16384):
        return agent.run_agent(self.pid, self.page, '把标题和段落都改了', 'k', 'm', intent='edit', stream=False,
                               max_tokens=max_tokens, context_budget=budget, on_event=self.events.append)

    def test_截断先放宽上限_同样的对话再来(self):
        self.script(CUT, CUT, msg(edit('#t', '新标题')), msg(REPORT))
        out = self.run_agent()
        self.assertTrue(out['changed'])
        self.assertEqual(self.limits[:3], [16384, 32768, 65536])
        self.assertEqual(len(self.sent[0]), len(self.sent[2]), '放宽重试不往对话里塞「拆小」')

    def test_放宽的上限服务不认_退回去改成拆小(self):
        self.script(CUT, DeepSeekError('DeepSeek HTTP 400: max_tokens too large'), msg(edit('#t', '新标题')), msg(REPORT))
        out = self.run_agent()
        self.assertTrue(out['changed'])
        self.assertEqual(self.limits[2], 16384)
        self.assertIn('拆小', self.sent[2][-1]['content'])

    def test_做完一步_对话长了就带着现在的页面重开(self):
        self.script(msg(PLAN), msg(edit('#t', '新标题')),
                    msg(('finish_step', {'step': 1, 'summary': '标题改成新标题，没有新名字'})),
                    msg(edit('#p', '新段落')), msg(('finish_step', {'step': 2, 'summary': '段落改好'})), msg(REPORT))
        out = self.run_agent(budget=2_000)   # 预算很小：做完一步就会重开
        self.assertTrue(out['changed'])
        after = self.sent[3]
        self.assertEqual(len(after), 2, '只剩系统提示和一条「接着做」')
        text = after[1]['content']
        self.assertIn('已经做完的步骤', text)
        self.assertIn('标题改成新标题', text)
        self.assertIn('新标题', text.split('<<<页面源码')[1], '带的是改过以后的页面')
        self.assertIn('现在做「改段落」', text)
        plans = [e for e in self.events if e.get('type') == 'plan']
        self.assertEqual([p['status'] for p in plans[-1]['steps']], ['done', 'done', 'active'])

    def test_对话不长就不重开(self):
        self.script(msg(PLAN), msg(edit('#t', '新标题')), msg(('finish_step', {'step': 1, 'summary': '标题'})), msg(REPORT))
        self.run_agent()
        self.assertGreater(len(self.sent[-1]), 3)

    def test_改和报做完放在同一条里_省一轮(self):
        self.script(msg(PLAN), msg(edit('#t', '新标题'), ('finish_step', {'step': 1, 'summary': '标题'})), msg(REPORT))
        out = self.run_agent()
        step = next(t for t in out['tool_log'] if t['tool'] == 'finish_step')['output']
        self.assertTrue(step['ok'])
        self.assertEqual(len(self.sent), 3)

    def test_同一条里修改没成功_这一步不算做完(self):
        bad = ('apply_operations', {'operations': [{'action': 'set_text', 'selector': '#nope', 'value': 'x'}]})
        self.script(msg(PLAN), msg(bad, ('finish_step', {'step': 1, 'summary': '标题'})), msg(REPORT))
        out = self.run_agent()
        step = next(t for t in out['tool_log'] if t['tool'] == 'finish_step')['output']
        self.assertFalse(step['ok'])
        self.assertIn('不算做完', step['error'])

    def test_继续_接着上一次的修改(self):
        storage.append_chat(self.pid, 'user', '新增一个停车管理页', {'page_id': self.page, 'intent': 'edit'})
        self.script(msg(edit('#t', '新标题')), msg(REPORT))
        out = agent.run_agent(self.pid, self.page, '继续', 'k', 'm', stream=False)
        self.assertEqual(out['intent'], 'edit')
        self.assertIn('接着把上一次没做完的做完', self.sent[0][-1]['content'])

    def test_没列计划不用finish_step(self):
        self.script(msg(edit('#t', '新标题')), msg(('finish_step', {'step': 1, 'summary': 'x'})), msg(REPORT))
        out = self.run_agent()
        step = next(t for t in out['tool_log'] if t['tool'] == 'finish_step')['output']
        self.assertFalse(step['ok'])

    def test_讨论模式没有这个工具(self):
        seen = []
        def chat(api_key, model, messages, tools, **k):
            seen.append({t['function']['name'] for t in tools})
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '看过了'}}]}
        agent.chat = chat
        agent.run_agent(self.pid, self.page, '这个页面怎么样', 'k', 'm', intent='discuss', stream=False)
        self.assertNotIn('finish_step', seen[0])


if __name__ == '__main__':
    unittest.main()
