"""架构模式：收拾数据、检查对不对得上、按依赖排生成顺序、交给 AI 的文字、接口、按架构生成时放进背景"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import architecture as A, storage, agent   # noqa: E402

try:
    from fastapi.testclient import TestClient
    from backend.server import app
    from backend.routes import architecture as routes
except Exception:   # 没装 fastapi 的环境跳过接口那几条
    TestClient = None


def device_arch():
    """智算组件库 · 设备管理：一个菜单下几个页签、数据成链、外部系统、手机端不做"""
    return {
        "name": "设备管理", "roles": ["管理员"],
        "nodes": [{"type": "module", "name": "设备管理", "children": [
            {"type": "page", "name": "设备巡检计划", "desc": "配点位、路线、计划", "children": [
                {"type": "tab", "name": "巡检计划", "desc": "周期 + 路线", "data": ["巡检计划"], "children": [
                    {"type": "modal", "name": "新增 / 编辑计划"}, {"type": "drawer", "name": "查看计划"}]},
                {"type": "tab", "name": "路线配置", "desc": "有序的一串点", "data": ["路线"]},
                {"type": "tab", "name": "巡检点", "desc": "在哪打卡", "data": ["巡检点"]}]},
            {"type": "page", "name": "设备录入", "desc": "按定义建档", "data": ["设备档案"]},
            {"type": "page", "name": "设备定义", "desc": "设备模板", "data": ["设备定义"]},
            {"type": "page", "name": "运维统计分析", "desc": "故障率"}]}],
        "entities": [
            {"name": "巡检计划", "fields": [{"name": "计划编号", "kind": "key"}, {"name": "路线", "kind": "ref", "ref": "路线"}]},
            {"name": "路线", "fields": [{"name": "巡检点", "kind": "ref", "ref": "巡检点"}, {"name": "点数", "kind": "derived", "note": "= 点的个数"}]},
            {"name": "巡检点", "fields": [{"name": "关联设备", "kind": "ref", "ref": "设备档案"}]},
            {"name": "设备档案", "fields": [{"name": "设备定义", "kind": "ref", "ref": "设备定义"}, {"name": "型号", "kind": "locked"}]},
            {"name": "设备定义", "fields": [{"name": "定义编码", "kind": "key"}]},
            {"name": "维修工单", "external": True, "fields": [{"name": "处理结果", "kind": "plain"}]}],
        "relations": [{"from": "路线", "to": "巡检计划", "label": "1 → N"}],
        "lanes": [{"name": "管理员", "kind": "user"}, {"name": "巡检执行", "kind": "skip", "note": "手机端 · 本次不做"}],
        "steps": [{"id": "s1", "lane": "管理员", "name": "配路线", "next": ["s2"]}, {"id": "s2", "lane": "巡检执行", "name": "逐点打卡"}],
    }


class 收拾数据(unittest.TestCase):
    def test_类型_编号_上限(self):
        arch = A.normalize({"nodes": [{"type": "什么", "name": "模块", "id": "n1", "children": [
            {"type": "page", "name": "页", "id": "n1"}, {"type": "page", "name": ""}]}], "steps": [{"name": "x", "lane": "不存在"}]})
        top = arch["nodes"][0]
        self.assertEqual(top["type"], "module")            # 最外层不认识的类型当模块
        self.assertEqual(len(top["children"]), 1)          # 没名字的丢掉
        self.assertNotEqual(top["children"][0]["id"], "n1")   # 编号重复换一个
        self.assertEqual(arch["steps"][0]["lane"], arch["lanes"][0]["id"])   # 泳道写错了落到第一条
        self.assertEqual(arch["rules"], A.PC_RULES)        # 没给规则就用电脑端统一规则
        self.assertEqual(arch["scope"], "pc")

    def test_泳道按名字对上(self):
        arch = A.normalize(device_arch())
        lanes = {l["name"]: l["id"] for l in arch["lanes"]}
        self.assertEqual(arch["steps"][1]["lane"], lanes["巡检执行"])
        self.assertEqual(arch["steps"][0]["next"], ["s1"][:0] + ["s2"])


class 顺序和检查(unittest.TestCase):
    def test_有页签的菜单页按页签算(self):
        names = [s["node"]["name"] for s in A.screens(A.normalize(device_arch()))]
        self.assertNotIn("设备巡检计划", names)
        self.assertIn("路线配置", names)

    def test_按数据依赖排(self):
        order = [s["name"] for s in A.order(A.normalize(device_arch()))]
        self.assertLess(order.index("设备定义"), order.index("设备录入"))
        self.assertLess(order.index("设备录入"), order.index("巡检点"))
        self.assertLess(order.index("巡检点"), order.index("路线配置"))
        self.assertLess(order.index("路线配置"), order.index("巡检计划"))
        self.assertEqual(order[-1], "运维统计分析")   # 没标数据的（统计、工作台）放最后：它们要用前面的数据

    def test_干净的架构没有错误(self):
        issues = A.check(A.normalize(device_arch()))
        self.assertEqual([i for i in issues if i["level"] == "error"], [])

    def test_引用不存在就报错(self):
        raw = device_arch()
        raw["entities"][2]["fields"][0]["ref"] = "设备台账"
        raw["nodes"][0]["children"][1]["data"] = ["不存在的数据"]
        texts = [i["text"] for i in A.check(A.normalize(raw)) if i["level"] == "error"]
        self.assertTrue(any("设备台账" in t for t in texts))
        self.assertTrue(any("不存在的数据" in t for t in texts))

    def test_环不会卡死(self):
        raw = {"entities": [{"name": "甲", "fields": [{"name": "x", "kind": "ref", "ref": "乙"}]},
                            {"name": "乙", "fields": [{"name": "y", "kind": "ref", "ref": "甲"}]}]}
        self.assertEqual(set(A.entity_ranks(A.normalize(raw))), {"甲", "乙"})


class 交给AI的文字(unittest.TestCase):
    def test_有树_数据_流程_规则_顺序(self):
        text = A.brief(A.normalize(device_arch()))
        for part in ("[页签] 路线配置", "关联设备（引用 设备档案）", "点数（自动算）", "外部系统", "本次不做",
                     "电脑端统一规则", "查看用右侧抽屉", "生成顺序：设备定义"):
            self.assertIn(part, text)

    def test_读得出模型的回复(self):
        self.assertEqual(A.parse_reply('```json\n{"name": "x"}\n```')["name"], "x")
        with self.assertRaises(ValueError):
            A.parse_reply("我不知道")

    def test_补全时沿用原来的编号(self):
        current = A.normalize(device_arch())
        old = current["nodes"][0]["id"]
        fresh = A.merge_ids({"nodes": [{"type": "module", "name": "设备管理"}]}, current)
        self.assertEqual(fresh["nodes"][0]["id"], old)


class 按架构生成(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat, self.old_stage = storage.DATA_ROOT, agent.chat, agent.stage
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text('<html><body><h1>x</h1></body></html>', encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        agent.stage = lambda *a, **k: {'pending_id': 'x'}
        self.sent = []

        def chat(api_key, model, messages, tools, **k):
            self.sent.append(json.dumps(messages, ensure_ascii=False))
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [
                {'id': 'c', 'type': 'function', 'function': {'name': 'report_result', 'arguments': json.dumps({'summary': '好', 'annotations': []})}}]}}]}
        agent.chat = chat

    def tearDown(self):
        storage.DATA_ROOT, agent.chat, agent.stage = self.old_root, self.old_chat, self.old_stage
        self.tmp.cleanup()

    def test_带上架构才放进背景(self):
        A.save(self.pid, device_arch())
        agent.run_agent(self.pid, self.page, '做页面', 'k', 'm', intent='edit', stream=False)
        self.assertNotIn('已确认的架构：设备管理', self.sent[-1])
        agent.run_agent(self.pid, self.page, '按架构生成', 'k', 'm', intent='edit', stream=False, architecture=True)
        self.assertIn('已确认的架构：设备管理', self.sent[-1])
        self.assertIn('生成顺序：设备定义', self.sent[-1])

    def test_系统提示里有电脑端统一规则(self):
        agent.run_agent(self.pid, self.page, '做页面', 'k', 'm', intent='edit', stream=False)
        self.assertIn('电脑端统一规则', self.sent[-1])


@unittest.skipIf(TestClient is None, "没装 fastapi")
class 接口(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat, self.old_load = storage.DATA_ROOT, routes.chat, routes.config.load
        storage.DATA_ROOT = Path(self.tmp.name)
        self.c = TestClient(app)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text('<html><body>x</body></html>', encoding='utf-8')
        storage.add_page(self.pid, 'index.html')

    def tearDown(self):
        storage.DATA_ROOT, routes.chat, routes.config.load = self.old_root, self.old_chat, self.old_load
        self.tmp.cleanup()

    def test_没有就是空的_存了能读回来(self):
        r = self.c.get(f'/api/projects/{self.pid}/architecture')
        self.assertEqual(r.json()['architecture'], None)
        r = self.c.put(f'/api/projects/{self.pid}/architecture', json={'architecture': device_arch()})
        self.assertEqual(r.status_code, 200)
        body = self.c.get(f'/api/projects/{self.pid}/architecture').json()
        self.assertEqual(body['architecture']['name'], '设备管理')
        self.assertEqual(body['order'][0]['name'], '设备定义')
        self.assertEqual(body['counts']['tabs'], 3)

    def test_AI起草(self):
        routes.config.load = lambda: {'api_key': 'k', 'model': 'm', 'base_url': 'u', 'max_tokens': 8000}
        seen = []
        def chat(key, model, messages, tools, **k):
            seen.append(messages[-1]['content'])
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(device_arch(), ensure_ascii=False)}}]}
        routes.chat = chat
        r = self.c.post(f'/api/projects/{self.pid}/architecture/draft', json={'mode': 'request', 'text': '做个设备巡检系统'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['architecture']['status'], 'draft')
        self.assertIn('设备巡检系统', seen[0])
        r = self.c.post(f'/api/projects/{self.pid}/architecture/draft', json={'mode': 'page'})
        self.assertIn('原型源码', seen[1])

    def test_回复读不出来给人话(self):
        routes.config.load = lambda: {'api_key': 'k', 'model': 'm', 'base_url': 'u', 'max_tokens': 8000}
        routes.chat = lambda *a, **k: {'choices': [{'finish_reason': 'length', 'message': {'content': '{"name": "半截'}}]}
        r = self.c.post(f'/api/projects/{self.pid}/architecture/draft', json={'mode': 'request', 'text': 'x'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('截断', r.text)


if __name__ == '__main__':
    unittest.main()
