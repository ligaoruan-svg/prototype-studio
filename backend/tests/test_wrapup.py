"""找不到该改的地方时：不再报「连续 8 轮都在读」收场，而是把查到的线索交给用户选；预览现场跟着需求一起交给 AI。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent   # noqa: E402


def call(name, args, i=0):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [{'id': f'c{i}', 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}}]}


class 收尾而不是报错(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, agent.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('收尾')['id']
        body = "\n".join(f"<p>第 {i} 行</p>" for i in range(400))
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(
            f"<html><head><title>t</title></head><body><nav><li>减碳项目管理</li></nav>{body}</body></html>", encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        self.seen_tools, self.seen_messages = [], []

    def tearDown(self):
        storage.DATA_ROOT, agent.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def fake(self, final):
        n = [0]
        def chat(api_key, model, messages, tools, **k):
            n[0] += 1
            names = {t['function']['name'] for t in tools}
            self.seen_tools.append(names)
            self.seen_messages.append(messages)
            if 'read_source_slice' in names:   # 一直在读，每次读不同的段
                return call('read_source_slice', {'start': n[0] * 20, 'end': n[0] * 20 + 10}, n[0])
            return final
        agent.chat = chat

    def test_一直在读_最后交出提问而不是报错(self):
        self.fake(call('ask_user', {'question': '我查到左侧菜单和页内按钮都能切到减碳项目管理，你说的是哪个？', 'options': ['左侧菜单', '页内按钮']}))
        out = agent.run_agent(self.pid, self.page, '点击页面没有反应', 'k', 'm', intent='edit', stream=False)
        self.assertFalse(out['changed'])
        self.assertTrue(out.get('clarification'))
        self.assertEqual(self.seen_tools[-1], {'ask_user', 'report_result'}, '收尾那一轮只能提问或汇报')
        self.assertLessEqual(len(self.seen_tools), agent.WRAPUP_AFTER + 1)

    def test_收尾轮用文字说明也算结论(self):
        self.fake({'choices': [{'finish_reason': 'stop', 'message': {'content': '查了侧栏和路由表，没找到点了不动的按钮，请在交互模式下点一遍再发。'}}]})
        out = agent.run_agent(self.pid, self.page, '点击页面没有反应', 'k', 'm', intent='edit', stream=False)
        self.assertFalse(out['changed'])
        self.assertIn('交互模式', out['report']['summary'])

    def test_预览现场写进背景(self):
        self.fake(call('report_result', {'summary': '看过了', 'annotations': []}))
        scene = {'route': '#abatement', 'clicks': [{'label': '减碳项目管理', 'tag': 'li', 'selector': 'nav li', 'hashBefore': '#analysis', 'hashAfter': '#abatement', 'changed': False, 'errors': ['renderAbatement is not defined']}]}
        agent.run_agent(self.pid, self.page, '点了没反应', 'k', 'm', intent='edit', stream=False, scene=scene)
        first_user = next(m for m in self.seen_messages[0] if m['role'] == 'user')['content']
        self.assertIn('点了「减碳项目管理」', first_user)
        self.assertIn('页面没有任何变化', first_user)
        self.assertIn('renderAbatement is not defined', first_user)


if __name__ == '__main__':
    unittest.main()


class 选中目标先对好行号(unittest.TestCase):
    SRC = "\n".join([
        "<script>",
        "const NAV=[{title:'碳配额管理',items:[['quota','企业碳配额总览'],['compliance','履约跟踪与预警']]}];",
        *["// 填充"] * 30,
        "function abatement(){return `<button class=\"btn\" data-action=\"measure-library\">节能减碳措施库</button>`}",
        *["// 填充"] * 30,
        "document.addEventListener('click',e=>{if(e.target.dataset.action==='measure-library')openLib()})",
        "</script>"])

    def test_脚本拼的按钮_按文字和data属性对到行(self):
        hints = agent.locate_lines(self.SRC, {'selector': 'div > button:nth-of-type(1)', 'text': '节能减碳措施库',
                                              'outer_html': '<button class="btn" data-action="measure-library">节能减碳措施库</button>'})
        self.assertEqual(hints[0]['line'], 33)
        self.assertIn('measure-library', hints[0]['matched'])
        self.assertIn(64, [h['line'] for h in hints], '处理点击的那一行也给出来')

    def test_对不上就不乱给(self):
        self.assertEqual(agent.locate_lines(self.SRC, {'selector': 'p', 'text': '完全不存在的字', 'outer_html': '<p>完全不存在的字</p>'}), [])
