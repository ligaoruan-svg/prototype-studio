"""每次运行留一份过程记录；计划只列一次、程序自动推进；快到轮次上限时提醒收尾。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent   # noqa: E402
from backend.tests.test_keep_work import msg, EDIT   # noqa: E402


class 运行记录(unittest.TestCase):
    PAGE = '<html><head><title>t</title></head><body><h1 id="t">旧标题</h1><p id="p">段落</p></body></html>'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT, agent.chat, agent.stage
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(self.PAGE, encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        agent.stage = lambda *a, **k: {'pending_id': 'x'}
        self.events = []

    def tearDown(self):
        storage.DATA_ROOT, agent.chat, agent.stage = self.old
        self.tmp.cleanup()

    def script(self, *replies):
        queue = list(replies); self.sent = []
        def chat(api_key, model, messages, tools, **k):
            self.sent.append([dict(m) for m in messages])
            r = queue.pop(0) if queue else msg(('report_result', {'summary': '完成'}))
            r.setdefault('usage', {'prompt_tokens': 100, 'completion_tokens': 10})
            return r
        agent.chat = chat

    def run_agent(self, **k):
        return agent.run_agent(self.pid, self.page, '把标题改成新标题', 'k', 'm', intent='edit', stream=False,
                               on_event=lambda e: self.events.append(json.loads(json.dumps(e))), **k)

    def traces(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((storage.project_dir(self.pid) / 'runs').glob('*.json'))]

    def test_每轮调了什么都记下来(self):
        bad = ('apply_operations', {'operations': [{'action': 'set_text', 'selector': '#nope', 'value': 'x'}]})
        self.script(msg(bad), msg(EDIT))
        self.run_agent()
        t = self.traces()[-1]
        self.assertTrue(t['outcome']['changed'])
        self.assertEqual([r['round'] for r in t['rounds']], [1, 2, 3])
        self.assertFalse(t['rounds'][0]['calls'][0]['ok'], '第一轮改错地方，记为失败')
        self.assertTrue(t['rounds'][0]['calls'][0]['error'])
        self.assertEqual(t['rounds'][1]['calls'][0]['tool'], 'apply_operations')
        self.assertEqual(t['rounds'][0]['prompt'], 100)

    def test_出错也留记录(self):
        def boom(*a, **k): raise RuntimeError('模型挂了')
        agent.chat = boom
        with self.assertRaises(Exception):
            self.run_agent()
        self.assertIn('模型挂了', self.traces()[-1]['outcome']['error'])

    def test_计划列一次_改一轮推一步(self):
        plan = ('update_plan', {'steps': [{'title': '改标题', 'status': 'active'}, {'title': '改段落', 'status': 'pending'}], 'brief': '谁用：值班员'})
        edit2 = ('apply_operations', {'operations': [{'action': 'set_text', 'selector': '#p', 'value': '新段落'}]})
        self.script(msg(plan), msg(EDIT), msg(edit2))
        self.run_agent()
        plans = [e for e in self.events if e.get('type') == 'plan']
        self.assertEqual(plans[0].get('brief'), '谁用：值班员', '业务梳理交给界面显示')
        self.assertEqual([s['status'] for s in plans[1]['steps']], ['done', 'active'])
        self.assertEqual([s['status'] for s in plans[2]['steps']], ['done', 'done'])
        tool_msgs = [m for m in self.sent[1] if m.get('role') == 'tool']
        self.assertIn('不用再调 update_plan', tool_msgs[-1]['content'])

    def test_快到上限提醒收尾(self):
        reads = [msg(('read_source_slice', {'start': i, 'end': i + 1})) for i in range(1, 9)]
        self.script(msg(EDIT), *reads)
        self.run_agent(max_rounds=8)
        joined = json.dumps(self.sent[-1], ensure_ascii=False)
        self.assertIn('只剩 3 轮', joined)


    def test_外壳刚放好不让翻源码(self):
        from backend import skill_digest
        shell = (ROOT / 'prompts/skills/零碳园区_UI_Skill包_v3/assets/页面外壳.html').read_text(encoding='utf-8')
        old = skill_digest.find_shell
        skill_digest.find_shell = lambda *a: ('零碳', 'assets/页面外壳.html', shell)
        try:
            add = ('apply_operations', {'operations': [{'action': 'shell_add', 'nav': "{key:'q',label:'配额',items:[{key:'quota',label:'配额'}]}",
                                                         'pages': "quota(){return pageShell('配额','','<p>配额</p>')}"}]})
            self.script(msg(('start_from_shell', {})), msg(('search_source', {'query': 'PA:NAV'})), msg(add))
            out = self.run_agent()
        finally:
            skill_digest.find_shell = old
        t = self.traces()[-1]
        self.assertTrue(t['rounds'][1]['calls'][0]['ok'], '搜关键词照常给：以前拦下，并发三个查询就凑满三次拒绝，整次失败')
        self.assertTrue(t['rounds'][2]['calls'][0]['ok'])
        self.assertTrue(out['changed'])

    def test_读了很久才动手_收尾时还能改(self):
        # 自检一次报六个问题：读了 6 轮源码才想好怎么改。以前收尾只给「提问 / 汇报」，
        # 它就自己编 replace_source_text 工具去调，连拒三次整次失败
        reads = [msg(('search_source', {'query': f'q{i}'})) for i in range(6)]
        self.script(*reads, msg(('replace_source_text', {'old': '旧标题', 'new': '新标题'})))
        out = self.run_agent()
        self.assertTrue(out['changed'])
        self.assertIn('不是单独的工具', self.sent[6][-1]['content'])   # 第 7 轮确实进了收尾，收尾里照样能改
        calls = [c for r in self.traces()[-1]['rounds'] for c in r['calls']]
        self.assertEqual(calls[-2]['tool'], 'apply_operations')   # 动作名当工具调的，替它包成了 apply_operations
        self.assertTrue(calls[-2]['ok'])
        self.assertEqual(calls[-1]['tool'], 'report_result')

    def test_选了风格_规范的视觉部分让给风格(self):
        self.script(msg(EDIT))
        self.run_agent()
        self.assertNotIn('以风格为准', self.sent[0][0]['content'])   # 以前的项目：规范照旧是全部视觉依据
        storage.set_style(self.pid, 'builtin:简洁后台')
        self.script(msg(EDIT))
        self.run_agent()
        system = self.sent[0][0]['content']
        self.assertIn('以风格为准', system)
        self.assertLess(system.index('以风格为准'), system.index('# 这个项目选的风格'))

    def test_外壳刚放好整份读给要点_连着读也不算拒绝(self):
        from backend import skill_digest
        shell = (ROOT / 'prompts/styles/数据大屏/assets/页面外壳.html').read_text(encoding='utf-8')
        old = skill_digest.find_shell
        skill_digest.find_shell = lambda *a: ('数据大屏', 'assets/页面外壳.html', shell)
        try:
            add = ('apply_operations', {'operations': [{'action': 'shell_add', 'nav': "{key:'q',label:'看板',items:[{key:'live',label:'实时'}]}",
                                                         'pages': "live(){return pageShell('实时','','<p>x</p>')}"}]})
            reads = [('inspect_page', {}), ('read_source_slice', {'start': 1, 'end': 50}), ('search_source', {'query': 'SVG.plus'}),
                     ('search_source', {'query': 'ZeroUI.Bars'})]
            self.script(msg(('start_from_shell', {})), msg(*reads), msg(add))
            out = self.run_agent()
        finally:
            skill_digest.find_shell = old
        calls = self.traces()[-1]['rounds'][1]['calls']
        self.assertTrue(all(c['ok'] for c in calls), calls)
        self.assertTrue(out['changed'])


if __name__ == '__main__':
    unittest.main()
