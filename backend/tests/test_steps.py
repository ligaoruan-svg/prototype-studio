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


class 做了哪几步跟着回复存下来(unittest.TestCase):
    """参照 Claude：回复上面「做了 N 步 · 用时」点开看每一步；刷新后还在（存在对话里）"""
    setUp, tearDown, script, run_agent = 一步一步.setUp, 一步一步.tearDown, 一步一步.script, 一步一步.run_agent
    def test_讨论回复带着步骤(self):
        self.script(msg(('search_source', {'query': '标题'})),
                    msg(('answer_user', {'answer': '标题偏小', 'suggestions': []})))
        agent.run_agent(self.pid, self.page, '标题怎么样？', 'k', 'm', intent='discuss', stream=False, on_event=self.events.append)
        last = storage.load_meta(self.pid)['chat'][-1]
        self.assertEqual([r['tool'] for r in last['trail']], ['search_source'])     # 整理回答那一步不算
        self.assertIn('找到', last['trail'][0]['detail'])
        self.assertIn('took', last)

    def test_改好的回复交给保存时也带上(self):
        kept = {}
        agent.stage = lambda *a, **k: kept.update(k) or {'pending_id': 'x'}
        self.script(msg(edit('#t', '新标题')), msg(REPORT))
        self.run_agent()
        self.assertEqual(kept['trail'][0]['tool'], 'apply_operations')

    def test_最后一段旁白是回答草稿_不重复存(self):
        def chat(api_key, model, messages, tools, **k):
            n = sum(1 for m in messages if m.get('role') == 'tool')
            if k.get('on_delta'):
                k['on_delta']('先查一下。' if n == 0 else '结论：标题偏小。\n- 字号：只有 14px', 'note')
            return msg(('search_source', {'query': '标题'})) if n == 0 else msg(('answer_user', {'answer': '结论：标题偏小', 'suggestions': []}))
        agent.chat = chat
        agent.run_agent(self.pid, self.page, '标题怎么样？', 'k', 'm', intent='discuss', stream=True, on_event=self.events.append)
        last = storage.load_meta(self.pid)['chat'][-1]
        self.assertEqual([r.get('note') or r.get('tool') for r in last['trail']], ['先查一下。', 'search_source'])

    def test_改代码那一步带着改了哪几行(self):
        self.script(msg(edit('#t', '新标题')), msg(REPORT))
        self.run_agent()
        done = next(e for e in self.events if e['type'] == 'step_done' and e.get('tool') == 'apply_operations')
        self.assertEqual((done['diff']['additions'], done['diff']['deletions']), (1, 1))
        self.assertEqual([l['kind'] for l in done['diff']['lines']], ['removed', 'added'])
        self.assertIn('新标题', done['diff']['lines'][1]['text'])

    def test_跑的时候补的话下一轮交给模型(self):
        box = [['标题用蓝色'], []]       # 第一轮开头还没人说话，第二轮开头补了一句
        self.script(msg(('search_source', {'query': '标题'})), msg(edit('#t', '新标题')), msg(REPORT))
        agent.run_agent(self.pid, self.page, '改标题', 'k', 'm', intent='edit', stream=False, on_event=self.events.append,
                        inbox=lambda: box.pop() if box else [])
        said = [m for m in self.sent[0] if m['role'] == 'user' and '标题用蓝色' in str(m['content'])]
        self.assertEqual(said, [])                                                      # 第一轮还没补
        later = [m for m in self.sent[1] if m['role'] == 'user' and '标题用蓝色' in str(m['content'])]
        self.assertEqual(len(later), 1)
        self.assertIn({'type': 'user_aside', 'text': '标题用蓝色'}, self.events)
        chat = storage.load_meta(self.pid)['chat']
        self.assertTrue(any(m.get('aside') and m['content'] == '标题用蓝色' for m in chat))   # 也记进对话


class 换一个回答(unittest.TestCase):
    """拿掉最后这一问一答再重跑；改过页面的、不是最后一条的不让换"""
    setUp, tearDown = 一步一步.setUp, 一步一步.tearDown

    def test_拿掉最后一问一答(self):
        storage.append_chat(self.pid, 'user', '标题怎么样', {'page_id': self.page})
        storage.append_chat(self.pid, 'assistant', '偏小', {'page_id': self.page, 'changed': False})
        storage.append_chat(self.pid, 'user', '颜色呢', {'page_id': self.page})
        storage.append_chat(self.pid, 'user', '顺便看看字号', {'page_id': self.page, 'aside': True})
        storage.append_chat(self.pid, 'assistant', '颜色可以', {'page_id': self.page, 'changed': False})
        chat = storage.load_meta(self.pid)['chat']
        with self.assertRaises(ValueError):
            storage.drop_turn(self.pid, chat[1]['id'])                     # 不是最后一条
        storage.drop_turn(self.pid, chat[-1]['id'])
        self.assertEqual([m['content'] for m in storage.load_meta(self.pid)['chat']], ['标题怎么样', '偏小'])

    def test_改过页面的不让换(self):
        storage.append_chat(self.pid, 'user', '改标题', {'page_id': self.page})
        storage.append_chat(self.pid, 'assistant', '改好了', {'page_id': self.page, 'changed': True})
        with self.assertRaises(ValueError):
            storage.drop_turn(self.pid, storage.load_meta(self.pid)['chat'][-1]['id'])
