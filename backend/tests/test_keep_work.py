"""已经改好、通过检查的修改不能因为后面一步出岔子就整轮丢掉；没改成的不能说成改好了。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent, transactions   # noqa: E402
from backend.patcher import apply_operations, new_issues, verify_source   # noqa: E402


def msg(*calls, finish='tool_calls'):
    return {'choices': [{'finish_reason': finish, 'message': {'content': '', 'tool_calls': [
        {'id': f'c{i}', 'type': 'function', 'function': {'name': n, 'arguments': a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)}}
        for i, (n, a) in enumerate(calls)]}}]}


EDIT = ('apply_operations', {'operations': [{'action': 'set_text', 'selector': '#t', 'value': '新标题'}]})


class 不丢修改(unittest.TestCase):
    PAGE = '<html><head><title>t</title></head><body><h1 id="t">旧标题</h1><div id="box"><p>保留我</p></div></body></html>'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat, self.old_stage = storage.DATA_ROOT, agent.chat, agent.stage
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(self.page_html(), encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        self.staged = []
        agent.stage = lambda pid, page, before, after, *a, **k: self.staged.append(after) or {'pending_id': 'x'}

    def page_html(self):
        return self.PAGE

    def tearDown(self):
        storage.DATA_ROOT, agent.chat, agent.stage = self.old_root, self.old_chat, self.old_stage
        self.tmp.cleanup()

    def script(self, *replies):
        queue = list(replies)
        self.sent = []
        def chat(api_key, model, messages, tools, **k):
            self.sent.append([dict(m) for m in messages])
            return queue.pop(0) if queue else msg(('report_result', {'summary': '完成'}))
        agent.chat = chat

    def run_agent(self, text='把标题改成新标题'):
        return agent.run_agent(self.pid, self.page, text, 'k', 'm', intent='edit', stream=False)

    def test_改完后三次输出超长_改动留着(self):
        cut = {'choices': [{'finish_reason': 'length', 'message': {'content': ''}}]}
        self.script(msg(EDIT), cut, cut, cut)
        out = self.run_agent()
        self.assertTrue(out['changed'])
        self.assertIn('新标题', self.staged[0])

    def test_参数是null不算内部错误(self):
        self.script(msg(EDIT), msg(('read_source_slice', {'start': None, 'end': None})))
        out = self.run_agent()
        self.assertTrue(out['changed'])
        self.assertEqual(len(self.staged), 1)

    def test_operations为null只是被拒(self):
        self.script(msg(('apply_operations', {'operations': None})), msg(EDIT))
        out = self.run_agent()
        self.assertTrue(out['changed'])

    def test_同一条里修改失败就不能报已完成(self):
        bad = ('apply_operations', {'operations': [{'action': 'set_text', 'selector': '#nope', 'value': 'x'}]})
        self.script(msg(bad, ('report_result', {'summary': '已把标题改好'})), msg(EDIT))
        out = self.run_agent()
        self.assertTrue(out['changed'], '第一次汇报被拦下，它重试了修改')
        tool_msgs = [m for m in self.sent[1] if m.get('role') == 'tool']
        self.assertIn('不能按「已改好」汇报', tool_msgs[-1]['content'])

    def test_组件放进容器里不清空原有内容(self):
        out, _ = apply_operations(不丢修改.PAGE, [{'action': 'append_html', 'selector': '#box', 'value': '<b>新</b>'}])
        self.assertIn('<p>保留我</p><b>新</b>', out)

    def test_没给的工具不执行(self):
        # 只讨论模式下修改类工具不在清单里：照抄着调也只会被拒
        tools_seen = []
        def chat(api_key, model, messages, tools, **k):
            tools_seen.append({t['function']['name'] for t in tools})
            if len(tools_seen) == 1:
                return msg(('apply_operations', EDIT[1]))
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '看过了，结构清楚。'}}]}
        agent.chat = chat
        out = agent.run_agent(self.pid, self.page, '这个页面怎么样', 'k', 'm', intent='discuss', stream=False)
        self.assertNotIn('apply_operations', tools_seen[0])
        self.assertFalse(out['changed'])
        self.assertEqual(self.staged, [])


class 自己写的代码一直记得(不丢修改):
    def test_改完好几轮后修改参数还在(self):
        # 以前两轮就收起：写完前一半，要一段段读回来才能接着写后一半
        big = ('apply_operations', {'operations': [{'action': 'set_html', 'selector': '#box', 'value': '<p>' + '新内容' * 1500 + '</p>'}]})
        reads = [msg(('read_source_slice', {'start': i, 'end': i + 2})) for i in (1, 3, 5)]
        self.script(msg(big), *reads)
        self.run_agent('把盒子内容换掉')
        last = self.sent[-1]
        args = [c['function']['arguments'] for m in last if m.get('role') == 'assistant' for c in m.get('tool_calls') or []]
        self.assertGreater(len(args[0]), 4000, '自己写的代码一直留在对话里')


class 源码读取不每轮收(不丢修改):
    PAGE = '<html><head><title>t</title></head><body>' + ''.join(f'<p id="p{i}">第 {i} 行 ' + 'x' * 120 + '</p>\n' for i in range(60)) + '<h1 id="t">旧标题</h1></body></html>'

    def test_读到的源码一直留着_快满了才收(self):
        reads = [msg(('read_source_slice', {'start': 1, 'end': 40}))] + [msg(('search_chats', {'query': f'词{i}'})) for i in range(4)]
        self.script(*reads, msg(EDIT), msg(('search_chats', {'query': 'a'})), msg(('search_chats', {'query': 'b'})), msg(('search_chats', {'query': 'c'})))
        self.run_agent()
        def slice_msg(sent):
            tools = [m for m in sent if m.get('role') == 'tool']
            return tools[0]['content'] if tools else ''
        self.assertNotIn('context_compacted', slice_msg(self.sent[5]), '读了源码、还在琢磨怎么改：原文要留着')
        self.assertNotIn('context_compacted', slice_msg(self.sent[-1]), '没到上下文预算就不收：对话只往后加，缓存才命中得了')

    def test_超过预算一次收到六成(self):
        from backend.experience import compact_once
        msgs = [{'role': 'system', 'content': 's' * 100}]
        for i in range(20):
            msgs.append({'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'read_source_slice', 'arguments': '{}'}}]})
            msgs.append({'role': 'tool', 'content': json.dumps({'content': 'x' * 5000})})
        size = lambda: sum(len(m.get('content') or '') + sum(len(c['function']['arguments']) for c in m.get('tool_calls') or []) for m in msgs)
        self.assertFalse(compact_once(msgs, 200_000), '没到预算不动')
        self.assertTrue(compact_once(msgs, 80_000))
        self.assertLessEqual(size(), 80_000 * 0.6 + 6000)
        self.assertIn('x' * 100, msgs[-1]['content'], '最近几条不动')
        self.assertFalse(compact_once(msgs, 80_000), '收完以后好几轮都不用再收')


class 页面原来就有的问题不拦(不丢修改):
    PAGE = ('<html><head><title>t</title></head><body><h1 id="t">旧标题</h1><i data-pid="a"></i><i data-pid="a"></i>'
            '<script>function (</script></body></html>')

    def test_原来就有重复pid和坏脚本_照样能改(self):
        self.script(msg(EDIT))
        out = self.run_agent()
        self.assertTrue(out['changed'])

    def test_新冒出来的问题照样拦(self):
        before = verify_source(self.PAGE)
        after = verify_source(self.PAGE.replace('</body>', '<script>let = ;</script></body>'))
        self.assertEqual(len(new_issues(before, after)), 1)
        self.assertEqual(new_issues(before, before), [])

    def test_提交时也按原来的问题算(self):
        after = self.PAGE.replace('旧标题', '新标题')
        out = self.old_stage(self.pid, self.page, self.PAGE, after, '改标题')
        self.assertTrue(out.get('changed', True))


if __name__ == '__main__':
    unittest.main()
