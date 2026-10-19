"""少读几轮源码：代码地图、预取片段、改完的落点、语法错误只修一处、缓存命中记账"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent   # noqa: E402
from backend.agent_source import _search_source   # noqa: E402
from backend.patcher import describe_syntax, verify_source   # noqa: E402
from backend.source_map import code_map, prefetch, changes_view, snip_line   # noqa: E402

LONG = "x" * 3000
PAGE = """<!doctype html><html><head><title>t</title>
<style>
.card{padding:8px}
</style>
</head><body>
<div id="app"></div>
<script>
const ORDER_DATA=[
{no:'A1',amount:1},
{no:'A2',amount:2}
];
const orderState={page:1};
function orderRows(){return ORDER_DATA.filter(o=>o.amount>0)}
const fmt=n=>String(n);
const NAV=[/*PA:NAV*/
  {key:'biz',label:'业务',items:[{key:'orders',label:'订单管理'},{key:'users',label:'用户管理'}]}
];
const Pages={/*PA:PAGES*/
  orders(){const pg=paginate(orderRows(),orderState.page,5);return `<table>${'%s'}</table>`},
  users(){return '<p>用户</p>'}
};
PageEvents.on('orders','click','[data-pid^="orderDel-"]',el=>{ORDER_DATA.pop()});
function bindPage(page){/*PA:BIND*/
  if(page==='orders'){document.getElementById('app').onclick=()=>{}}
}
</script>
</body></html>""" % LONG


def call(name, args, i=0, usage=None):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [{'id': f'c{i}', 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}}], 'usage': usage or {}}


class 代码地图(unittest.TestCase):
    def test_函数页面数据和绑定都有行号(self):
        text = code_map(PAGE)
        lines = PAGE.splitlines()
        self.assertIn(f"L{lines.index('function orderRows(){return ORDER_DATA.filter(o=>o.amount>0)}') + 1} function orderRows()", text)
        self.assertIn("const ORDER_DATA=[…（2 行数据）", text)
        self.assertIn("NAV 菜单：biz 业务、orders 订单管理、users 用户管理", text)
        self.assertIn("orders L", text)
        self.assertIn("字）", text, "一行几千字的函数要标出来")
        self.assertIn("PageEvents.on('orders','click','[data-pid^=\"orderDel-\"]')", text)
        self.assertIn("分页：orders L", text)
        self.assertIn("<div#app>", text)
        self.assertNotIn(LONG[:200], text, "地图只给名字，不给正文")

    def test_太长就截断(self):
        many = "<html><body><script>\n" + "\n".join(f"function f{i}(a,b){{}}" for i in range(2000)) + "\n</script></body></html>"
        self.assertLessEqual(len(code_map(many)), 4100)


class 预取(unittest.TestCase):
    def test_报错里的名字和用户点名的函数先找出来(self):
        text = prefetch(PAGE, ["直接打开「订单管理」就报错：Uncaught ReferenceError: paginate is not defined"])
        self.assertIn("paginate", text)
        self.assertIn("orders(){const pg=paginate(", text)
        self.assertLess(len(text), 7000)

    def test_到处都有的词不算(self):
        self.assertEqual(prefetch(PAGE, ["把 Math.max 和 document 都看看"]), "")

    def test_点选的行号也带上(self):
        n = PAGE.splitlines().index("const fmt=n=>String(n);") + 1
        self.assertIn("const fmt=n=>String(n);", prefetch(PAGE, ["这里不对"], [n]))


class 搜索结果变小(unittest.TestCase):
    def test_长行只给命中附近(self):
        out = _search_source(PAGE, "paginate")
        self.assertEqual(out["hits"], 1)
        self.assertLess(len(out["context"]), 3000)
        self.assertIn("这一行共", out["context"])
        self.assertIn("paginate(orderRows()", out["context"])

    def test_短行原样(self):
        self.assertEqual(snip_line("abc", "b"), "abc")


class 语法错误说清楚(unittest.TestCase):
    def test_页面行号列号和前后原文(self):
        src = "<!doctype html><html><head><title>t</title></head><body>\n<script>\nconst a=1;\nfunction x(){return [1].map(v=>v)).join()}\n</script></body></html>"
        issues = verify_source(src)["issues"]
        if not verify_source("<html><head></head><body><script>(</script></body></html>")["syntax_checked"]:
            self.skipTest("没有 node")
        self.assertEqual(len(issues), 1)
        self.assertIn("页面第 4 行", issues[0])
        self.assertIn("SyntaxError", issues[0])
        self.assertIn("⟪这里⟫", issues[0])

    def test_长行不再把错误信息截掉(self):
        raw = "[stdin]:3\n" + "a" * 5000 + "\n" + " " * 4000 + "^\n\nSyntaxError: Unexpected token ')'\n    at x"
        text = describe_syntax(raw, 10)
        self.assertIn("页面第 12 行第 4001 列 SyntaxError: Unexpected token ')'", text)
        self.assertLess(len(text), 600)


class 改完的落点(unittest.TestCase):
    def test_新增几行和行号挪动(self):
        old = "a\nb\nc"
        view = changes_view(old, "a\nb\nnew1\nnew2\nc")
        self.assertEqual(view["shift"], 2)
        self.assertIn("现在的第 3–4 行（新增）", view["changed"][0])


class 循环里(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, agent.chat
        storage.DATA_ROOT = Path(self.tmp.name) / "projects"
        storage.DATA_ROOT.mkdir(parents=True)
        self.pid = storage.create_project('省轮次')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text(PAGE, encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']
        self.sent = []

    def tearDown(self):
        storage.DATA_ROOT, agent.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def script(self, steps):
        it = iter(steps)
        def fake(api_key, model, messages, tools, **k):
            self.sent.append(json.loads(json.dumps(messages, ensure_ascii=False)))
            return next(it)
        agent.chat = fake

    def test_第一条消息带代码地图和预取片段(self):
        self.script([call('report_result', {'summary': '看过了', 'annotations': []})])
        agent.run_agent(self.pid, self.page, '订单管理报错：paginate is not defined', 'k', 'm', intent='edit', stream=False)
        kickoff = self.sent[0][-1]["content"]
        self.assertIn("代码地图", kickoff)
        self.assertIn("function orderRows()", kickoff)
        self.assertIn("预先在源码里找到的片段", kickoff)
        self.assertIn("orders(){const pg=paginate(", kickoff)

    def test_改完返回落点_缓存命中记账(self):
        self.script([
            call('apply_operations', {'operations': [{'action': 'replace_source_text', 'old': 'const orderState={page:1};',
                                                      'new': 'const orderState={page:1};\nfunction paginate(r,p,s){return {rows:r}}'}]}, 1,
                 {'prompt_tokens': 1000, 'completion_tokens': 10, 'total_tokens': 1010, 'prompt_cache_hit_tokens': 800}),
            call('report_result', {'summary': '补上了', 'annotations': []}, 2,
                 {'prompt_tokens': 1200, 'completion_tokens': 10, 'total_tokens': 1210, 'prompt_tokens_details': {'cached_tokens': 1000}})])
        out = agent.run_agent(self.pid, self.page, '补上 paginate', 'k', 'm', intent='edit', stream=False)
        self.assertTrue(out['changed'])
        applied = next(t for t in out['tool_log'] if t['tool'] == 'apply_operations')['output']
        self.assertIn("现在的第", applied['where']['changed'][0])
        self.assertIn("function paginate", applied['where']['changed'][0])
        self.assertEqual(out['usage']['cached_tokens'], 1800)
        self.assertEqual(out['usage']['prompt_tokens'], 2200)

    def test_语法错误暂存_下一次只修出错处(self):
        if not verify_source("<html><head></head><body><script>(</script></body></html>")["syntax_checked"]:
            self.skipTest("没有 node")
        big = "function report(){return [1,2,3].map(v=>v*2)).join(',')}\n" + "\n".join(f"function extra{i}(){{return {i}}}" for i in range(40))
        self.script([
            call('apply_operations', {'operations': [{'action': 'replace_source_text', 'old': 'const fmt=n=>String(n);',
                                                      'new': 'const fmt=n=>String(n);\n' + big}]}, 1),
            call('apply_operations', {'operations': [{'action': 'replace_source_text', 'old': 'v=>v*2)).join',
                                                      'new': 'v=>v*2).join'}]}, 2),
            call('report_result', {'summary': '加好了', 'annotations': []}, 3)])
        out = agent.run_agent(self.pid, self.page, '加一个报表函数', 'k', 'm', intent='edit', stream=False)
        first, second = [t['output'] for t in out['tool_log'] if t['tool'] == 'apply_operations']
        self.assertFalse(first['ok'])
        self.assertIn("暂存", first['error'])
        self.assertIn("⟪这里⟫", first['error'])
        self.assertTrue(second['ok'], second)
        self.assertTrue(out['changed'])
        view = "\n".join(second['where']['changed'])
        self.assertIn("function report(){return [1,2,3].map(v=>v*2).join", view, "暂存的整段连同修正一起写进页面")
        self.assertIn("这段共 41 行", view)

    def test_暂存后整段重发也行_不会写两遍(self):
        if not verify_source("<html><head></head><body><script>(</script></body></html>")["syntax_checked"]:
            self.skipTest("没有 node")
        bad = 'const fmt=n=>String(n);\nfunction report(){return [1].map(v=>v)).join()}'
        good = 'const fmt=n=>String(n);\nfunction report(){return [1].map(v=>v).join()}'
        self.script([
            call('apply_operations', {'operations': [{'action': 'replace_source_text', 'old': 'const fmt=n=>String(n);', 'new': bad}]}, 1),
            call('apply_operations', {'operations': [{'action': 'replace_source_text', 'old': 'const fmt=n=>String(n);', 'new': good}]}, 2),
            call('report_result', {'summary': '加好了', 'annotations': []}, 3)])
        out = agent.run_agent(self.pid, self.page, '加一个报表函数', 'k', 'm', intent='edit', stream=False)
        second = [t['output'] for t in out['tool_log'] if t['tool'] == 'apply_operations'][1]
        self.assertTrue(second['ok'], second)
        view = "\n".join(second['where']['changed'])
        self.assertEqual(view.count("function report()"), 1)


if __name__ == "__main__":
    unittest.main()
