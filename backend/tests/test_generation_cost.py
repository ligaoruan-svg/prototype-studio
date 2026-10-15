"""从零生成一页别再烧几十万 tokens：规范要点常驻、大文件不给整份读、外壳由程序复制、读过的大段过两轮就收起。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent, skills, skill_digest   # noqa: E402

SKILL = "零碳园区_UI_Skill包_v3"


def call(name, args, i=0):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [{'id': f'c{i}', 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}}]}


@unittest.skipUnless((skills.ROOT / SKILL).exists(), "没装零碳园区 skill")
class 生成省钱(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, agent.chat
        storage.DATA_ROOT = Path(self.tmp.name) / "projects"
        storage.DATA_ROOT.mkdir(parents=True)
        self.pid = storage.create_project('生成')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(
            "<!doctype html><html><head><title>测试</title></head><body><main><h1>从一个想法开始</h1></main></body></html>", encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        self.sizes, self.tools_seen = [], []

    def tearDown(self):
        storage.DATA_ROOT, agent.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def script(self, steps):
        it = iter(steps)
        def fake(api_key, model, messages, tools, **k):
            self.sizes.append(sum(len(json.dumps(m, ensure_ascii=False)) for m in messages))
            self.tools_seen.append({t['function']['name'] for t in tools or []})
            return next(it)
        agent.chat = fake

    def test_要点在系统提示里_大文件不给整份读(self):
        block = skills.index_block()
        self.assertIn("组件签名", block)
        self.assertIn("ZeroUI" if "ZeroUI" in block else "Modal(", block)
        self.assertNotIn("页面外壳.html 的要点", block, "外壳由程序整份复制，不用摘")
        self.script([call('read_skill_file', {'name': SKILL, 'path': 'assets/零碳园区_UI组件库.html'}, 1),
                     call('report_result', {'summary': '看过了', 'annotations': []}, 2)])
        out = agent.run_agent(self.pid, self.page, '看一下组件库', 'k', 'm', intent='edit', stream=False)
        read = next(t for t in out['tool_log'] if t['tool'] == 'read_skill_file')['output']
        self.assertTrue(read.get('whole_file_refused'))
        self.assertTrue(read['outline'] == [] or isinstance(read['outline'], list))

    def test_从外壳起步_只写三处(self):
        shell = skill_digest.find_shell()[2]
        self.script([
            call('start_from_shell', {}, 1),
            call('apply_operations', {'operations': [{'action': 'replace_source_text',
                 'old': "  {key:'biz',label:'业务模块',items:[{key:'home',label:'首页'}]}",
                 'new': "  {key:'dev',label:'设备管理',items:[{key:'inspect',label:'设备巡检'}]}"},
                {'action': 'replace_source_text',
                 'old': "  home(){return pageShell('首页','',`${Card({title:'内容',body:'在这里写这一页的内容'})}`)}",
                 'new': "  inspect(){return pageShell('设备巡检管理','',`${Card({title:'设备台账',body:'表格'})}`)}"}]}, 2),
            call('report_result', {'summary': '做好了', 'annotations': []}, 3)])
        out = agent.run_agent(self.pid, self.page, '从零做一个设备巡检管理页', 'k', 'm', intent='edit', stream=False)
        self.assertTrue(out['changed'])
        self.assertIn('start_from_shell', self.tools_seen[0])
        self.assertLess(self.sizes[-1] - self.sizes[0], 6000, "外壳 3 万字由程序放进页面，不进对话")
        self.assertGreater(len(shell), 20000)

    def test_页面已有内容不许整页换外壳(self):
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text("<html><body>" + "<p>已有内容</p>" * 2000 + "</body></html>", encoding='utf-8')
        self.script([call('start_from_shell', {}, 1), call('report_result', {'summary': '没换', 'annotations': []}, 2)])
        out = agent.run_agent(self.pid, self.page, '整页重做', 'k', 'm', intent='edit', stream=False)
        self.assertFalse(out['changed'])
        self.assertFalse(out['tool_log'][0]['output']['ok'])

    def test_读过的大段过两轮就收起(self):
        steps = [call('read_skill_file', {'name': SKILL, 'path': 'references/零碳园区_UI规范.md', 'start': 808, 'end': 1000}, 1)]
        steps += [call('search_source', {'query': f'第{i}个'}, i + 2) for i in range(3)]
        steps += [call('report_result', {'summary': '看完了', 'annotations': []}, 9)]
        self.script(steps)
        agent.run_agent(self.pid, self.page, '看看表格规范', 'k', 'm', intent='edit', stream=False)
        self.assertLess(self.sizes[-1], self.sizes[1], "规范那一节读完两轮后收起，后面每步不再带着它")


if __name__ == "__main__":
    unittest.main()
