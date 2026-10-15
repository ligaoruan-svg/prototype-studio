"""AI 修改主线的三个兜底：服务忙自动重试、中途出错保住已改好的部分、用户能停下。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent, deepseek_client   # noqa: E402
from backend.deepseek_client import DeepSeekError    # noqa: E402
from backend.errors import WorkError                 # noqa: E402


class 自动重试(unittest.TestCase):
    def setUp(self):
        self.old = (deepseek_client._chat_once, deepseek_client.RETRY_DELAYS)
        deepseek_client.RETRY_DELAYS = (0, 0, 0)

    def tearDown(self):
        deepseek_client._chat_once, deepseek_client.RETRY_DELAYS = self.old

    def fake(self, failures):
        calls = []
        def once(*a, **k):
            calls.append(1)
            if len(calls) <= len(failures):
                raise failures[len(calls) - 1]
            return {'choices': [{'message': {'content': 'ok'}}]}
        deepseek_client._chat_once = once
        return calls

    def test_限流和5xx等一下再来(self):
        calls = self.fake([DeepSeekError('DeepSeek HTTP 503: Service Unavailable'), DeepSeekError('curl: (22) The requested URL returned error: 429')])
        retries = []
        out = deepseek_client.chat('k', 'm', [], on_retry=lambda n, w, e: retries.append(n))
        self.assertEqual(out['choices'][0]['message']['content'], 'ok')
        self.assertEqual(len(calls), 3)
        self.assertEqual(retries, [1, 2])

    def test_密钥和余额问题不重试(self):
        calls = self.fake([DeepSeekError('DeepSeek HTTP 401: invalid api key')])
        with self.assertRaises(DeepSeekError):
            deepseek_client.chat('k', 'm', [])
        self.assertEqual(len(calls), 1)

    def test_重试用完报繁忙(self):
        self.fake([DeepSeekError('模型网络错误: timed out', 'network')] * 4)
        with self.assertRaises(DeepSeekError) as ctx:
            deepseek_client.chat('k', 'm', [])
        self.assertEqual(ctx.exception.code, 'busy')

    def test_等待重试时点了停止立刻停(self):
        deepseek_client.RETRY_DELAYS = (5, 5, 5)
        self.fake([DeepSeekError('HTTP 502 bad gateway')] * 4)
        with self.assertRaises(DeepSeekError) as ctx:
            deepseek_client.chat('k', 'm', [], should_stop=lambda: True)
        self.assertEqual(ctx.exception.code, 'stopped')


EDIT = {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {
    'name': 'apply_operations', 'arguments': json.dumps({'operations': [{'action': 'replace_source_text', 'old': '保存', 'new': '确认新增'}]}, ensure_ascii=False)}}]}}]}


class 中途出错和停止(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, agent.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('兜底')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(
            "<html><head><title>t</title></head><body><button id='b'>保存</button></body></html>", encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']

    def tearDown(self):
        storage.DATA_ROOT, agent.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def script(self, *steps):
        it = iter(steps)
        def fake(*a, **k):
            step = next(it)
            if isinstance(step, Exception):
                raise step
            return step
        agent.chat = fake

    def test_改到一半模型断了_已改的部分保留(self):
        self.script(EDIT, DeepSeekError('模型服务暂时不可用，已自动重试 3 次', 'busy'))
        out = agent.run_agent(self.pid, self.page, '把保存改成确认新增', 'k', 'm', intent='edit', stream=False)
        self.assertTrue(out['changed'])
        self.assertIn('中途出错', out['report']['summary'])
        self.assertTrue(out.get('pending_id') or out.get('token') or out.get('preview_url'), '已改好的部分要交给检查和保存')

    def test_还没改就断了_照常报错(self):
        self.script(DeepSeekError('模型服务暂时不可用', 'busy'))
        with self.assertRaises(DeepSeekError):
            agent.run_agent(self.pid, self.page, '改一下', 'k', 'm', intent='edit', stream=False)

    def test_改完一处后点停止_已改的保留(self):
        self.script(EDIT, EDIT)
        checks = []
        def should_stop():   # 第一轮开头、执行工具前各问一次都不停；第二轮开头时用户已经点了停止
            checks.append(1)
            return len(checks) >= 3
        out = agent.run_agent(self.pid, self.page, '把保存改成确认新增', 'k', 'm', intent='edit', stream=False, should_stop=should_stop)
        self.assertTrue(out['changed'])
        self.assertIn('你停止了这次处理', out['report']['summary'])

    def test_一开始就停_报已停止(self):
        self.script(EDIT)
        with self.assertRaises(WorkError) as ctx:
            agent.run_agent(self.pid, self.page, '改一下', 'k', 'm', intent='edit', stream=False, should_stop=lambda: True)
        self.assertEqual(ctx.exception.code, 'stopped')


if __name__ == '__main__':
    unittest.main()
