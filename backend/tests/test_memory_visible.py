"""项目记忆要用得上：没有记忆时也告诉 AI 什么时候该记；像约定的话开场提醒；记住了要回到结果里给用户看。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent, memory   # noqa: E402


class 记忆看得见(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, agent.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('记忆')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text("<html><body><button>保存</button></body></html>", encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']

    def tearDown(self):
        storage.DATA_ROOT, agent.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def test_没有记忆时系统提示里也有怎么记(self):
        self.assertIn('remember', memory.index_block({'memory': []}))

    def test_像约定的话才提醒(self):
        self.assertTrue(memory.looks_like_rule('以后按钮都用描边'))
        self.assertTrue(memory.looks_like_rule('别再用渐变了'))
        self.assertFalse(memory.looks_like_rule('把这个按钮改成蓝色'))

    def test_记住的约定回到结果里(self):
        seen = []
        steps = iter([
            {'choices': [{'message': {'content': '', 'tool_calls': [{'id': 'a', 'type': 'function', 'function': {'name': 'remember', 'arguments': json.dumps({'note': '按钮一律用描边样式'}, ensure_ascii=False)}}]}}]},
            {'choices': [{'message': {'content': '', 'tool_calls': [{'id': 'b', 'type': 'function', 'function': {'name': 'report_result', 'arguments': json.dumps({'summary': '记下了', 'annotations': []}, ensure_ascii=False)}}]}}]},
        ])
        def fake(api_key, model, messages, tools, **k):
            seen.append([dict(m) for m in messages])
            return next(steps)
        agent.chat = fake
        out = agent.run_agent(self.pid, self.page, '以后按钮都用描边', 'k', 'm', intent='edit', stream=False)
        self.assertEqual([r['text'] for r in out['report']['remembered']], ['按钮一律用描边样式'])
        self.assertIn('长期有效的约定', seen[0][-1]['content'])
        chat = storage.load_meta(self.pid)['chat']
        self.assertEqual(chat[-1]['report']['remembered'][0]['text'], '按钮一律用描边样式', '刷新后卡片上还看得到')


if __name__ == '__main__':
    unittest.main()
