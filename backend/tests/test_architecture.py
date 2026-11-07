"""架构模式：收拾数据、检查对不对得上、按依赖排生成顺序、交给 AI 的文字、接口、按架构生成时放进背景"""
import sys
import tempfile
import copy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import architecture as A, arch_text as T, arch_expand as D, storage, agent   # noqa: E402

try:
    from fastapi.testclient import TestClient
    from backend.server import app
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
    def test_一个菜单页一步_页签算在页面里(self):
        screens = A.screens(A.normalize(device_arch()))
        names = [s["node"]["name"] for s in screens]
        self.assertIn("设备巡检计划", names)
        self.assertNotIn("路线配置", names)
        plan = next(s for s in screens if s["node"]["name"] == "设备巡检计划")
        self.assertEqual(plan["tabs"], ["巡检计划", "路线配置", "巡检点"])
        self.assertEqual(set(plan["data"]), {"巡检计划", "路线", "巡检点"})

    def test_按数据依赖排(self):
        order = [s["name"] for s in A.order(A.normalize(device_arch()))]
        self.assertLess(order.index("设备定义"), order.index("设备录入"))
        self.assertLess(order.index("设备录入"), order.index("设备巡检计划"))
        self.assertEqual(order[-1], "运维统计分析")   # 没标数据的（统计、工作台）放最后：它们要用前面的数据

    def test_干净的架构没有错误(self):
        issues = A.check(A.normalize(device_arch()))
        self.assertEqual([i for i in issues if i["level"] == "error"], [])

    def test_数据对不上只提醒_不挡生成(self):
        raw = device_arch()
        raw["entities"][2]["fields"][0]["ref"] = "设备台账"
        raw["nodes"][0]["children"][1]["data"] = ["不存在的数据"]
        issues = A.check(A.normalize(raw))
        data = [i for i in issues if i.get("area") == "data"]
        self.assertTrue(any("设备台账" in i["text"] for i in data))
        self.assertTrue(any("不存在的数据" in i["text"] for i in data))
        self.assertFalse(any(i["level"] == "error" for i in data))
        self.assertFalse(any("没有页面用到" in i["text"] for i in issues))

    def test_环不会卡死(self):
        raw = {"entities": [{"name": "甲", "fields": [{"name": "x", "kind": "ref", "ref": "乙"}]},
                            {"name": "乙", "fields": [{"name": "y", "kind": "ref", "ref": "甲"}]}]}
        self.assertEqual(set(A.entity_ranks(A.normalize(raw))), {"甲", "乙"})


class 交给AI的文字(unittest.TestCase):
    def test_有树_数据_流程_规则_顺序(self):
        text = A.brief(A.normalize(device_arch()))
        for part in ("[页签] 路线配置", "关联设备（引用 设备档案）", "点数（自动算）", "外部系统", "本次不做",
                     "电脑端统一规则", "查看用右侧抽屉"):
            self.assertIn(part, text)

    def test_重读时沿用原来的编号(self):
        current = A.normalize(device_arch())
        old = current["nodes"][0]["id"]
        fresh = T.keep_ids({"nodes": [{"type": "module", "name": "设备管理"}]}, current)
        self.assertEqual(fresh["nodes"][0]["id"], old)


class 大纲(unittest.TestCase):
    def test_写出去读回来一模一样(self):
        arch = A.normalize(device_arch())
        arch["nodes"][0]["children"][1]["tags"] = ["联动：改了 A，B 跟着变、C 也变"]
        arch["lanes"][0]["note"] = "电脑、看结果"
        text = T.to_outline(arch)
        back = A.normalize(T.keep_ids(T.from_outline(text), arch))
        self.assertEqual(T.to_outline(back), text)
        self.assertEqual([s["next"] for s in back["steps"]], [s["next"] for s in arch["steps"]])
        self.assertEqual(back["nodes"][0]["id"], arch["nodes"][0]["id"])   # 路径没变的沿用编号

    def test_手写_缩进几格都行_类型按层级猜(self):
        arch = A.normalize(T.from_outline("设备管理\n    设备定义：模板\n        新增定义 [弹窗]\n    设备录入 | 数据：设备档案、设备定义\n巡检"))
        top = arch["nodes"]
        self.assertEqual([n["name"] for n in top], ["设备管理", "巡检"])
        self.assertEqual(top[0]["type"], "module")
        self.assertEqual(top[0]["children"][0]["type"], "page")
        self.assertEqual(top[0]["children"][0]["desc"], "模板")
        self.assertEqual(top[0]["children"][0]["children"][0]["type"], "modal")
        self.assertEqual(top[0]["children"][1]["data"], ["设备档案", "设备定义"])

    def test_数据字段的写法(self):
        arch = A.normalize(T.from_outline("【数据】\n因子 FAC-D-xxx / FAC-I-xx [配置]：排放因子\n  因子编号 🔑\n  因子库 → 因子库：1 个\n  合计 = 各行相加\n  单位 🔒 来自模板\n  备注\n  状态：草稿 → 启用"))
        e = arch["entities"][0]
        self.assertEqual((e["name"], e["code"], e["role"]), ("因子", "FAC-D-xxx / FAC-I-xx", "配置"))
        self.assertEqual([f["kind"] for f in e["fields"]], ["key", "ref", "derived", "locked", "plain"])
        self.assertEqual(e["fields"][1]["ref"], "因子库")
        self.assertEqual(e["states"], ["草稿", "启用"])


class 分到弹什么(unittest.TestCase):
    def test_按钮_弹窗字段_表格列_写出去读回来(self):
        text = ("模板详情 [下钻页] | 入口：点模板名称\n"
                "  顶部操作栏 [区块]\n"
                "    行业模板库 [按钮] | 打开：选择行业模板\n"
                "    删除设施/活动 [按钮] | 二次确认：删除后不能恢复 | 出现：勾选了才能点\n"
                "  选择行业模板 [弹窗] | 字段：行业*、模板版本 | 确认后：活动数据行按行业模板覆盖\n"
                "  固定燃烧源 [表格] | 列：设施/活动、排放源\n"
                "    编辑 [按钮] | 打开：不存在的弹窗\n")
        arch = A.normalize(T.from_outline(text))
        bar = arch["nodes"][0]["children"][0]
        self.assertEqual(bar["children"][0]["action"], "open")
        self.assertEqual(bar["children"][0]["target"], "选择行业模板")
        self.assertEqual((bar["children"][1]["action"], bar["children"][1]["when"]), ("confirm", "勾选了才能点"))
        layer = arch["nodes"][0]["children"][1]
        self.assertEqual(layer["fields"], ["行业*", "模板版本"])
        self.assertIn("覆盖", layer["after"])
        self.assertEqual(arch["nodes"][0]["children"][2]["cols"], ["设施/活动", "排放源"])
        self.assertEqual(T.to_outline(A.normalize(T.from_outline(T.to_outline(arch)))), T.to_outline(arch))
        warns = [i["text"] for i in A.check(arch)]
        self.assertTrue(any("不存在的弹窗" in w for w in warns))        # 按钮打开的东西找不到要提醒
        self.assertFalse(any("选择行业模板" in w for w in warns))
        self.assertIn("点了：打开「选择行业模板」", A.brief(arch))
        self.assertIn("字段：行业*、模板版本", A.brief(arch))

    def test_照展开图拆到按钮和弹窗(self):
        page = {"type": "page", "name": "碳排核算模板配置", "children": []}
        html = "<label>年度<select><option>2026</option></select></label><table><tr><th>序号</th><th>模板编号</th><th>状态</th><th>操作</th></tr></table>"
        nodes = [
            {"id": 1, "parent": None, "label": "新增模板", "title": "新增核算模板", "html": "<label>模板名称*</label><label>行业</label>"},
            {"id": 2, "parent": None, "label": "表格行 · TMP-BUILD-2026-V2", "title": "TMP-BUILD-2026-V2", "kind": "subpage", "html": "<th>设施/活动</th>"},
            {"id": 3, "parent": 2, "label": "新增子类别", "title": "新增子类别", "html": "<label>子类别名称</label>"},
            {"id": 4, "parent": None, "label": "页签 · GWP值", "title": "GWP值", "kind": "subpage", "html": ""},
        ]
        D._fill(page, html, nodes, None)
        kinds = [(c["type"], c["name"]) for c in page["children"]]
        self.assertIn(("block", "筛选"), kinds)                              # 上面有表格：这排输入框是筛选
        self.assertIn(("table", "碳排核算模板列表"), kinds)                    # 表格上面没标题：页面名 + 列表
        self.assertIn(("button", "新增模板"), kinds)
        self.assertIn(("modal", "新增核算模板"), kinds)
        self.assertIn(("drill", "碳排核算模板详情"), kinds)          # 编号当标题的详情页换成「xx详情」
        self.assertIn(("tab", "GWP值"), kinds)
        table = next(c for c in page["children"] if c["type"] == "table")
        self.assertEqual(table["cols"], ["模板编号", "状态"])
        self.assertEqual(table["children"][0]["action"], "jump")       # 表格行里的按钮挂在表格下面
        modal = next(c for c in page["children"] if c["type"] == "modal")
        self.assertEqual(modal["fields"], ["模板名称*", "行业"])
        drill = next(c for c in page["children"] if c["type"] == "drill")
        self.assertIn("TMP-BUILD-2026-V2", drill["entry"])
        self.assertTrue(any(c["type"] == "button" and c["name"] == "新增子类别" for c in drill["children"]))


    def test_每一行点开的同一个详情只记一次(self):
        page = {"type": "page", "name": "报修工单", "children": []}
        html = ("<table><tr><th>工单号</th><th>状态</th><th>操作</th></tr>"
                "<tr><td><a>BX-011</a></td><td><span>待派单</span></td><td><button>详情</button><button>派单</button></td></tr>"
                "<tr><td><a>BX-010</a></td><td><span>待派单</span></td><td><button>详情</button><button>派单</button></td></tr></table>")
        drawer = ('<div class="drawer-mask" id="activeDrawer"><section role="dialog" aria-label="工单详情"><div class="drawer-hd"><b>工单详情</b></div>'
                  '<dl><dt>工单号</dt><dd>BX-011</dd><dt>报修人</dt><dd>李四</dd></dl><div class="sec-title">现场照片</div></section></div>')
        nodes = [
            {"id": 1, "parent": None, "label": "表格行 · BX-011", "title": "现场照片", "layerSel": "#activeDrawer", "html": drawer, "also": ["表格行 · 详情"]},
            {"id": 2, "parent": None, "label": "表格行 · BX-010", "title": "现场照片", "layerSel": "#activeDrawer", "html": drawer.replace("011", "010")},
            {"id": 3, "parent": None, "label": "表格行 · 派单", "title": "派单", "layerSel": "#activeModal",
             "html": '<section role="dialog" aria-label="派单"><dt>工单号</dt><label>指派给<span class="req">*</span></label></section>'},
        ]
        D._fill(page, html, nodes, None)
        layers = [(c["type"], c["name"]) for c in page["children"] if c["type"] in ("drawer", "modal")]
        self.assertEqual(layers, [("drawer", "工单详情"), ("modal", "派单")])     # 标题取抽屉头，不取正文小节；只一张
        table = next(c for c in page["children"] if c["type"] == "table")
        self.assertEqual([b["name"] for b in table["children"]], ["工单号", "详情", "派单"])   # 编号按钮叫那一列的名字；「派单」不会认成「待派单」那一列
        self.assertEqual(page["children"][-2]["fields"], ["工单号", "报修人"])
        self.assertEqual(page["children"][-1]["fields"], ["工单号🔒", "指派给*"])


@unittest.skipIf(TestClient is None, "没装 fastapi")
class 接口(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.c = TestClient(app)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text('<html><body>x</body></html>', encoding='utf-8')
        storage.add_page(self.pid, 'index.html')

    def tearDown(self):
        storage.DATA_ROOT = self.old_root
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

    def test_同步做完_这几处记成已同步(self):
        url = f'/api/projects/{self.pid}/architecture'
        base = A.save(self.pid, {"nodes": [{"type": "page", "name": "报修工单", "proto": True, "seen": True}]})["nodes"]
        A.save_base(self.pid, base)
        arch = A.load(self.pid)
        arch["nodes"] += [{"type": "page", "name": "维修工"}, {"type": "page", "name": "统计"}]
        arch = self.c.put(url, json={'architecture': arch}).json()['architecture']
        repair, stats = arch['nodes'][1], arch['nodes'][2]
        r = self.c.post(url + '/accept', json={'ids': [repair['id']]}).json()
        self.assertEqual([n['name'] for n in r['base']], ['报修工单', '维修工'])        # 只记同步了的那一处
        self.assertTrue(r['architecture']['nodes'][1].get('proto'))                    # 不再是虚线
        self.assertFalse(r['architecture']['nodes'][2].get('proto'))                   # 没同步的照旧

    def test_界面存画布不会冲掉业务梳理(self):
        url = f'/api/projects/{self.pid}/architecture'
        A.save(self.pid, {"nodes": [], "spec": {"roles": [{"name": "客服"}], "objects": [{"name": "工单"}]}})
        r = self.c.put(url, json={'architecture': {"nodes": [{"type": "page", "name": "工单"}]}}).json()
        self.assertEqual(r['architecture']['spec']['objects'][0]['name'], '工单')

    def test_从原型读_画布上没同步的改动留着(self):
        page = storage.load_meta(self.pid)['pages'][0]['id']
        url = f'/api/projects/{self.pid}/architecture'
        self.assertEqual(self.c.post(url + '/refresh', json={}).json()['reason'], 'no_expand')   # 没展开过：什么都不动
        storage.save_expand_routes(self.pid, page, [{'hash': '#order', 'title': '报修工单'}, {'hash': '#test', 'title': '测试'}])
        storage.save_expand_entry(self.pid, page, '#order', 'h', {'page': '<table><tr><th>工单号</th></tr></table>', 'nodes': []})
        r = self.c.post(url + '/refresh', json={}).json()
        self.assertTrue(r['refreshed'])
        self.assertEqual([n['name'] for n in r['architecture']['nodes']], ['报修工单', '测试'])   # 没分组的菜单项放最外层
        self.assertEqual(r['base'], r['architecture']['nodes'])                               # 刚读完：画布就是原型的样子
        # 画布上：写介绍、删掉「测试」、规划一页「维修工」；原型没变，再读一次，这些都还在
        arch = r['architecture']
        arch['nodes'][0]['desc'] = '接单派单'
        arch['nodes'] = [arch['nodes'][0], {'type': 'page', 'name': '维修工'}]
        self.c.put(url, json={'architecture': arch})
        r = self.c.post(url + '/refresh', json={}).json()
        self.assertEqual([n['name'] for n in r['architecture']['nodes']], ['报修工单', '维修工'])
        self.assertEqual(r['architecture']['nodes'][0]['desc'], '接单派单')
        self.assertIn('（规划中，原型里还没有）', A.brief(r['architecture']))


class 和原型对齐(unittest.TestCase):
    """画布 = base（上次从原型读的样子）+ 画布上还没同步的改动；再读原型时改动重放上去"""
    def fresh(self, *pages, fields=None):
        return [{"type": "page", "name": n, "children": [{"type": "modal", "name": "新增", "fields": (fields or {}).get(n, ["名称*"])}]} for n in pages]

    def test_改名_删掉_规划_改字段_都留着_AI改好了就对上(self):
        canvas, base = D.refresh_canvas([], None, self.fresh("报修工单", "测试", "统计"))
        self.assertEqual(D.diff(base, canvas), [])
        import copy
        canvas = copy.deepcopy(canvas)
        canvas[0]["name"] = "报修单"                                    # 改名
        canvas[0]["children"][0]["fields"] = ["名称*", "备注"]           # 改字段
        del canvas[1]                                                   # 删掉「测试」
        canvas.append({"id": "nplan01", "type": "page", "name": "维修工", "children": [{"id": "nplan02", "type": "modal", "name": "新增", "fields": ["名称*"]}]})   # 规划
        canvas[1]["desc"] = "按月看"                                     # 只写在画布上的介绍
        ops = D.diff(base, canvas)
        self.assertEqual(sorted(o["op"] for o in ops), ["add", "edit", "remove", "rename"])
        # 原型没变，再读：改动都还在，删掉的不会补回来，改名的不会变成两个
        again, base2 = D.refresh_canvas(canvas, base, self.fresh("报修工单", "测试", "统计"))
        self.assertEqual([n["name"] for n in again], ["报修单", "统计", "维修工"])
        self.assertEqual(again[0]["children"][0]["fields"], ["名称*", "备注"])
        self.assertEqual(again[1]["desc"], "按月看")
        self.assertFalse(again[2].get("seen"))
        # AI 照着改好了：原型里就是这个样子，再读一次，没有要同步的了；编号都没变
        done, base3 = D.refresh_canvas(again, base2, self.fresh("报修单", "统计", "维修工", fields={"报修单": ["名称*", "备注"]}))
        self.assertEqual([n["name"] for n in done], ["报修单", "统计", "维修工"])
        self.assertEqual(done[0]["id"], canvas[0]["id"])
        self.assertTrue(done[2].get("proto"))
        self.assertEqual(D.diff(base3, done), [])

    def test_原型里删掉的_画布上留着标出来(self):
        canvas, base = D.refresh_canvas([], None, self.fresh("报修工单", "测试"))
        tree, base2 = D.refresh_canvas(canvas, base, self.fresh("报修工单"))
        self.assertEqual([n["name"] for n in tree], ["报修工单", "测试"])
        self.assertTrue(D.gone(tree[1]))
        self.assertEqual(D.diff(base2, tree), [])                       # 不算要同步的改动
        tree2, _ = D.refresh_canvas([tree[0]], base2, self.fresh("报修工单"))   # 你删了它：就没了
        self.assertEqual([n["name"] for n in tree2], ["报修工单"])


class 字段控件(unittest.TestCase):
    def test_照原型认控件(self):
        from backend.arch_fields import form_fields, parse_field
        html = ('<div class="field"><label for="a">报修人<span class="req">*</span></label><select id="a"><option>请选择报修人</option><option>张三（YZ-001）</option><option>李四</option></select></div>'
                '<div class="field"><label>联系电话</label><input type="text" readonly placeholder="选择报修人后自动带出"></div>'
                '<div class="field"><label>预计上门时间<span class="req">*</span></label><input placeholder="YYYY-MM-DD HH:mm"></div>'
                '<label>是否加急</label><label><input type="radio">是</label><label><input type="radio">否</label>'
                '<label>报修事项</label><input type="text"><label>问题描述</label><textarea></textarea>')
        self.assertEqual(form_fields(html), ["报修人*（下拉：张三/李四）", "联系电话🔒", "预计上门时间*", "是否加急（单选：是/否）", "报修事项", "问题描述"])
        self.assertEqual(parse_field("报修人*（下拉：张三（YZ-001）/李四）")["options"], ["张三（YZ-001）", "李四"])
        self.assertEqual(parse_field("预计上门时间*")["type"], "datetime")

    def test_大纲里括号里的顿号不切开_按钮目标带补充也认(self):
        arch = A.normalize(T.from_outline("【页面】\n报修 [模块]\n  工单 [菜单页]\n    新增 [按钮] | 打开：新增工单（业主来电代录）\n"
                                          "    新增工单 [弹窗] | 字段：分类*（下拉：给排水、电气）、备注\n【数据】\n工单\n业主提交 [外部]\n【关系】\n业主提交 [外部] → 工单：1 → 1"))
        modal = arch["nodes"][0]["children"][0]["children"][1]
        self.assertEqual(modal["fields"], ["分类*（下拉：给排水、电气）", "备注"])
        self.assertEqual(arch["relations"][0]["from"], "业主提交")
        self.assertEqual([i for i in A.check(arch) if i["level"] == "error"], [])
        self.assertFalse(any("在架构里没有" in i["text"] for i in A.check(arch)))

    def test_空模块自己就是一个页面_照用户的生成(self):
        arch = A.normalize(T.from_outline("【页面】\n报修 [模块]\n  工单 [菜单页]：派单\n测试 [模块]"))
        self.assertEqual([o["name"] for o in A.order(arch)], ["工单", "测试"])
        self.assertFalse(any("下面还没有页面" in i["text"] for i in A.check(arch)))
        self.assertFalse(any(i["level"] == "error" for i in A.check(arch)))


class 架构模式对话(unittest.TestCase):
    def setUp(self):
        from backend import arch_chat
        self.mod = arch_chat
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, arch_chat.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('物业')['id']

    def tearDown(self):
        storage.DATA_ROOT, self.mod.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def test_只改页面树_编号和原型标记跟着走(self):
        saved = A.save(self.pid, {"nodes": [{"type": "page", "name": "报修工单", "proto": True, "seen": True,
                                              "children": [{"type": "modal", "name": "派单", "fields": ["指派给*"], "proto": True, "seen": True}]}]})
        seen = []
        def chat(key, model, messages, tools, **k):
            seen.append(messages[-1]['content'])
            k['on_delta']('x' * 300)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content':
                    '说明：加了「维修工」菜单页，派单弹窗加了预计上门时间。\n\n【页面】\n报修工单 [菜单页]\n  派单 [弹窗] | 字段：指派给*（选人）、预计上门时间*\n维修工 [菜单页]：管理维修工'}}]}
        self.mod.chat = chat
        events = []
        out = self.mod.run(self.pid, 'p', '加一个维修工页', 'k', 'm', 'u', 8000, events.append, lambda: False)
        self.assertTrue(out['content'].startswith('加了「维修工」菜单页，派单弹窗加了预计上门时间。'))
        self.assertIn('报修工单 [菜单页]', seen[0])                        # 现在的树交给模型
        self.assertTrue(any('已写' in e.get('label', '') for e in events))
        arch = A.load(self.pid)
        page, new = arch['nodes']
        self.assertEqual(page['id'], saved['nodes'][0]['id'])
        self.assertTrue(page.get('proto'))
        self.assertEqual(page['children'][0]['fields'], ['指派给*（选人）', '预计上门时间*'])
        self.assertFalse(new.get('seen'))                                   # 新规划的：原型里还没有
        with self.assertRaises(Exception):
            self.mod.chat = lambda *a, **k: {'choices': [{'finish_reason': 'length', 'message': {'content': ''}}]}
            self.mod.run(self.pid, 'p', 'x', 'k', 'm', 'u', 8000, events.append, lambda: False)


    def test_问的只回答_页面树不动_建议点了才改(self):
        A.save(self.pid, {"nodes": [{"type": "page", "name": "报修工单", "proto": True, "seen": True}]})
        before = A.load(self.pid)
        seen = []
        def ask(key, model, messages, tools, **k):
            seen.append(messages)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content':
                    '结构基本清楚，但少了维修工管理。\n\n- 报修工单只有一页，派单要找人时没处可看\n\n可以这样改：\n- 加维修工页｜左侧多一个维修工菜单页｜在最外层新增菜单页「维修工」：管理维修工\n- 随便写的一行'}}]}
        self.mod.chat = ask
        out = self.mod.run(self.pid, 'p', '分析一下架构', 'k', 'm', 'u', 8000, lambda e: None, lambda: False)
        self.assertFalse(out['architecture_changed'])
        self.assertEqual(A.load(self.pid)['nodes'], before['nodes'])                  # 一点没动
        self.assertNotIn('整份', seen[0][0]['content'])                                # 用的是回答的提示词
        self.assertEqual(out['discussion']['suggestions'][0]['label'], '加维修工页')
        self.assertTrue(out['discussion']['arch'])
        self.assertNotIn('可以这样改', out['discussion']['answer'])
        # 点「按这个改」：照建议改页面树，而且看得到上一轮说了什么
        def edit(key, model, messages, tools, **k):
            seen.append(messages)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '说明：加了维修工页。\n\n【页面】\n报修工单 [菜单页]\n维修工 [菜单页]：管理维修工'}}]}
        self.mod.chat = edit
        out = self.mod.run(self.pid, 'p', '按已讨论的建议修改：在最外层新增菜单页「维修工」', 'k', 'm', 'u', 8000, lambda e: None, lambda: False)
        self.assertTrue(out['architecture_changed'])
        self.assertEqual([n['name'] for n in A.load(self.pid)['nodes']], ['报修工单', '维修工'])
        self.assertTrue(any('少了维修工管理' in m['content'] for m in seen[1] if m['role'] == 'assistant'))


SPEC_REPLY = """好的，梳理如下：
```json
{"summary": "物业报修管理后台", "roles": [{"name": "物业客服", "does": "受理、派单"}, {"name": "维修工", "does": "接单、完工"}],
 "objects": [{"name": "报修工单", "desc": "业主报的一次维修", "owner": "物业客服", "states": ["待派单", "处理中", "已完成"],
              "actions": ["派单：待派单→处理中（客服）", "完工：处理中→已完成（维修工）"]},
             {"name": "租户", "states": []}],
 "flows": ["报修 → 派单 → 完工"], "rules": ["紧急工单 30 分钟内派单"],
 "scope": {"in": ["报修派单"], "out": ["业主小程序"], "external": []},
 "assumptions": ["费用只记录"], "questions": [{"q": "维修工要登录后台吗？", "options": ["要", "不要"]}, {"q": "只有一个选项的不算", "options": ["x"]}]}
```"""


class 业务梳理(unittest.TestCase):
    def setUp(self):
        from backend import arch_chat
        self.mod = arch_chat
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, arch_chat.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('物业')['id']
        self.seen = []

    def tearDown(self):
        storage.DATA_ROOT, self.mod.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def answer(self, content):
        def chat(key, model, messages, tools, **k):
            self.seen.append(messages)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}
        self.mod.chat = chat

    def say(self, text):
        self.mark = len(self.seen)          # 这一轮的第一次调模型（后面可能还有自动检查修的那一次）
        return self.mod.run(self.pid, 'p', text, 'k', 'm', 'u', 16000, lambda e: None, lambda: False)

    def test_读梳理(self):
        from backend import arch_spec as S
        spec = S.parse(SPEC_REPLY)
        self.assertEqual([r["name"] for r in spec["roles"]], ["物业客服", "维修工"])
        self.assertEqual(spec["objects"][0]["states"], ["待派单", "处理中", "已完成"])
        self.assertEqual(len(spec["questions"]), 1)                       # 只有一个选项的问题不算
        self.assertIsNone(S.parse("没有 JSON"))
        self.assertIn("动作：派单：待派单→处理中（客服）", S.to_text(spec))
        for yes in ("可以", "好的，画吧", "就这样", "直接画", "确认", "好的，按这个来", "ok 画吧", "嗯，就这样", "没问题，开始"):
            self.assertTrue(S.is_confirm(yes), yes)
        for no in ("租户这次不做", "可以再加一个角色吗", "不行", "好的，但是费用要做"):
            self.assertFalse(S.is_confirm(no), no)
        # 模型常犯的 JSON 小毛病：注释、多余的逗号
        loose = '{"roles": [{"name": "客服", "does": "看 http://x"},], // 角色\n "objects": [{"name": "工单",}],}'
        self.assertEqual(S.parse(loose)["roles"][0]["does"], "看 http://x")

    def test_贴需求先梳理_改一句_确认了再画(self):
        self.answer(SPEC_REPLY)
        out = self.say("物业报修管理系统\n业主报修，客服派单\n维修工上门完工")
        self.assertEqual(out["spec"]["objects"][0]["name"], "报修工单")
        self.assertFalse(out["architecture_changed"])
        self.assertIn("业务梳理清楚", self.seen[self.mark][0]["content"])                   # 用的是梳理的提示词
        arch = A.load(self.pid)
        self.assertEqual(arch["nodes"], [])                                    # 画布不动
        self.assertEqual(arch["spec"]["status"], "draft")
        # 梳理卡还没确认：再说一句是在改梳理
        self.answer(SPEC_REPLY.replace('{"name": "租户", "states": []}', '{"name": "维修工档案"}'))
        out = self.say("租户这次不做，加上维修工档案")
        self.assertIn("上一版梳理", self.seen[self.mark][-1]["content"])
        self.assertTrue(out["content"].startswith("按你的意思改了梳理"))
        # 确认：按梳理画，带着产品规则
        self.answer("说明：按梳理画了报修管理。\n\n【页面】\n报修管理 [模块]\n  报修工单 [菜单页]\n    工单列表 [表格] | 列：工单号、状态\n      派单 [按钮] | 出现：状态是待派单时")
        out = self.say("按业务梳理画架构\n问题回答：\n- 维修工要登录后台吗？：要")
        self.assertTrue(out["architecture_changed"])
        self.assertIn("按业务梳理画页面树的规则", self.seen[self.mark][0]["content"])
        self.assertIn("业务梳理（用户已确认）", self.seen[self.mark][-1]["content"])
        arch = A.load(self.pid)
        self.assertEqual(arch["nodes"][0]["name"], "报修管理")
        self.assertEqual(arch["spec"]["status"], "confirmed")
        self.assertEqual(arch["roles"], ["物业客服", "维修工"])
        # 画完以后的小改：直接改，梳理当依据带上
        self.answer("说明：加了维修工页。\n\n【页面】\n报修管理 [模块]\n  报修工单 [菜单页]\n  维修工 [菜单页]")
        out = self.say("加一个维修工页")
        self.assertTrue(out["architecture_changed"])
        self.assertIn("业务梳理（用户已确认）", self.seen[self.mark][-1]["content"])
        self.assertNotIn("业务梳理清楚", self.seen[self.mark][0]["content"])

    def test_中间问一句_梳理卡还等着确认(self):
        self.answer(SPEC_REPLY)
        self.say("物业报修管理系统")
        self.answer("三个角色分别负责受理、维修、管理。")
        out = self.say("为什么要分三个角色？")
        self.assertIn("discussion", out)
        self.answer("说明：画好了。\n\n【页面】\n报修管理 [模块]\n  报修工单 [菜单页]")
        out = self.say("就这样")
        self.assertTrue(out["architecture_changed"])
        self.assertEqual(A.load(self.pid)["spec"]["status"], "confirmed")

    def test_有画布时说可以_不是确认梳理(self):
        A.save(self.pid, {"nodes": [{"type": "page", "name": "报修工单"}]})
        self.assertNotEqual(self.mod.stage_of("可以", None, A.load(self.pid), None), "draw")      # 没有待确认的梳理卡
        spec = {"status": "draft", "roles": [{"name": "客服", "does": ""}]}
        self.assertEqual(self.mod.stage_of("费用这次不做", None, A.load(self.pid), spec), "spec")       # 等确认时说的是在改梳理
        self.assertEqual(self.mod.stage_of("为什么要分三个角色？", None, A.load(self.pid), spec), "ask")
        self.assertEqual(self.mod.stage_of("就这样", None, A.load(self.pid), spec), "draw")
        self.assertEqual(self.mod.stage_of("梳理一下架构", None, A.load(self.pid), None), "spec")
        self.assertEqual(self.mod.stage_of("这样分合理吗？", None, A.load(self.pid), None), "ask")


def repair_tree():
    return A.normalize({"nodes": [
        {"type": "module", "name": "报修管理", "proto": True, "seen": True, "desc": "我写的介绍", "children": [
            {"type": "page", "name": "报修工单", "proto": True, "seen": True, "children": [
                {"type": "table", "name": "工单列表", "cols": ["工单号"], "proto": True, "seen": True, "children": [
                    {"type": "button", "name": "派单", "action": "open", "target": "派单", "proto": True, "seen": True}]},
                {"type": "modal", "name": "派单", "fields": ["维修工*"], "proto": True, "seen": True}]},
            {"type": "page", "name": "费用单"}]},
        {"type": "page", "name": "统计"}]})


class 只改动到的地方(unittest.TestCase):
    def test_改动照着改_改名留着编号和原型标记(self):
        from backend import arch_ops as O
        tree = repair_tree()["nodes"]
        ids = {n["name"]: n["id"] for n, _, _ in A.walk(tree)}
        _, kind, body = O.split_reply("""说明：改了几处。

【改动】
+ 在「报修管理」下面：
    维修工 [菜单页]：管理维修工
      维修工列表 [表格] | 列：姓名、电话
- 删掉「报修管理 / 费用单」
~ 「报修工单」改名为「工单管理」
> 把「统计」挪到「报修管理」下面
* 改「工单列表」：列：工单号、状态 | 介绍：所有工单
* 改「派单」：出现：状态是待派单时
* 改「派单 [弹窗]」：字段：维修工*（选人）、预计上门时间*（日期时间）
> 把「报修管理」挪到「工单列表」下面
- 删掉「不存在的页」""")
        self.assertEqual(kind, "ops")
        new, done, failed = O.apply_ops(tree, O.parse_ops(body))
        flat = {n["name"]: n for n, _, _ in A.walk(new)}
        self.assertEqual(flat["工单管理"]["id"], ids["报修工单"])               # 改名不换编号
        self.assertTrue(flat["工单管理"]["proto"])                              # 原型里有的标记还在
        self.assertEqual(flat["工单列表"]["cols"], ["工单号", "状态"])
        self.assertEqual(flat["报修管理"]["desc"], "我写的介绍")                 # 没提到的一个字不动
        self.assertNotIn("费用单", flat)
        self.assertIn("维修工列表", flat)
        self.assertEqual([n["name"] for n in new], ["报修管理"])                 # 统计挪进去了
        # 挪进自己下面、找不到的、重名分不清的（按钮和弹窗都叫「派单」）：跳过并说出来
        self.assertEqual(len(failed), 3)
        self.assertTrue(any("没找到「派单」" in f for f in failed))
        modal = next(n for n, _, _ in A.walk(new) if n["type"] == "modal")
        self.assertEqual(modal["fields"], ["维修工*（选人）", "预计上门时间*（日期时间）"])           # 带上类型就分得清
        self.assertEqual(len(tree), 2)                                         # 原来那份没被改

    def test_自动检查(self):
        from backend import arch_ops as O
        arch = repair_tree()
        arch["nodes"][0]["children"][0]["children"][0]["children"][0]["target"] = "指派维修工"
        arch["nodes"][0]["children"][1]["children"] = [{"id": "nx1", "type": "table", "name": "列表", "children": []}]
        arch["spec"] = {"objects": [{"name": "报修工单", "actions": ["派单：待派单→处理中", "关闭：待派单→已关闭"]},
                                    {"name": "维修工档案", "actions": []}, {"name": "收费单", "actions": []}],
                        "scope": {"external": ["收费单由收费系统回传"]}}
        found = O.problems(arch)
        self.assertTrue(any("指派维修工" in p for p in found))                  # 按钮要打开的不存在
        self.assertTrue(any("叫「列表」" in p for p in found))
        self.assertTrue(any("「关闭」这个动作没有按钮" in p for p in found))
        self.assertTrue(any("维修工档案" in p for p in found))
        self.assertFalse(any("收费单" in p for p in found))                     # 外部系统的不查
        self.assertFalse(any("「派单」这个动作" in p for p in found))


class 架构小改与自动修(unittest.TestCase):
    def setUp(self):
        from backend import arch_chat
        self.mod = arch_chat
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, arch_chat.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('物业')['id']
        A.save(self.pid, repair_tree())

    def tearDown(self):
        storage.DATA_ROOT, self.mod.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def test_小改只动一处_检查出的问题自动修一轮(self):
        replies = ["说明：加了关闭按钮。\n\n【改动】\n+ 在「工单列表」下面：\n    关闭 [按钮] | 打开：关闭工单",
                   "说明：补上关闭工单弹窗。\n\n【改动】\n+ 在「报修工单」下面：\n    关闭工单 [弹窗] | 字段：关闭原因*（多行）"]
        seen = []
        def chat(key, model, messages, tools, **k):
            seen.append(messages)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': replies[len(seen) - 1]}}]}
        self.mod.chat = chat
        before = {n["id"]: n for n, _, _ in A.walk(A.load(self.pid)["nodes"])}
        out = self.mod.run(self.pid, 'p', '工单列表加一个关闭按钮', 'k', 'm', 'u', 16000, lambda e: None, lambda: False)
        self.assertIn("【改动】", seen[0][0]["content"])                        # 小改用改动格式
        self.assertIn("关闭工单」在页面树里没有", seen[1][-1]["content"])          # 检查出来的交给 AI 修
        self.assertIn("自动修了 1 处", out["content"])
        after = {n["id"]: n for n, _, _ in A.walk(A.load(self.pid)["nodes"])}
        for nid, node in before.items():                                       # 原来的节点一个没少、属性没变
            self.assertEqual({k: v for k, v in after[nid].items() if k != "children"}, {k: v for k, v in node.items() if k != "children"})
        self.assertEqual({n["name"] for n in after.values()} - {n["name"] for n in before.values()}, {"关闭", "关闭工单"})


class 架构小改不冲掉刚读进来的(unittest.TestCase):
    def setUp(self):
        from backend import arch_chat
        self.mod = arch_chat
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_chat = storage.DATA_ROOT, arch_chat.chat
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('物业')['id']
        A.save(self.pid, repair_tree())

    def tearDown(self):
        storage.DATA_ROOT, self.mod.chat = self.old_root, self.old_chat
        self.tmp.cleanup()

    def test_模型想的时候画布从原型补了一页(self):
        def chat(key, model, messages, tools, **k):
            arch = A.load(self.pid)                       # 模拟：这时候从原型读完，补进来一页
            arch["nodes"].append({"type": "page", "name": "巡检记录", "proto": True, "seen": True})
            A.save(self.pid, arch)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': "说明：改名。\n\n【改动】\n~ 「统计」改名为「统计分析」"}}]}
        self.mod.chat = chat
        self.mod.run(self.pid, 'p', '把统计改名为统计分析', 'k', 'm', 'u', 16000, lambda e: None, lambda: False)
        names = [n["name"] for n in A.load(self.pid)["nodes"]]
        self.assertIn("巡检记录", names)
        self.assertIn("统计分析", names)


class 架构AI的小毛病(unittest.TestCase):
    def test_该走哪条路(self):
        from backend import arch_chat as C
        cur = A.normalize({"nodes": [{"type": "module", "name": "报修管理", "children": [{"type": "page", "name": "报修工单"}, {"type": "page", "name": "费用单"}]}]})
        cases = [("这个设计架构合理吗？", "ask"), ("能帮我出个架构吗？", "spec"), ("帮我梳理下架构", "spec"), ("分析一下架构", "ask"),
                 ("1. 加一个维修工页到报修管理\n2. 删掉费用单\n3. 报修工单改名为工单管理", "edit"),          # 一行一条的修改是小改
                 ("物业系统需求：\n业主报修，客服派单\n维修工上门处理\n主管看统计", "spec")]
        for text, want in cases:
            self.assertEqual(C.stage_of(text, None, cur, None), want, text)
        self.assertEqual(C.arch_mode("继续画完", "draw", False), "edit")

    def test_改动行的各种写法都认(self):
        from backend import arch_ops as O
        _, kind, body = O.split_reply("说明：改了\n## 改动\n1. + 在「报修管理」下面新增：\n    维修工 [菜单页]\n2. - 删除「费用单」\n"
                                      "3. ~ “报修工单”改成“工单管理”\n- ~ 「统计」重命名为「统计分析」\n4. > 把「统计分析」移到「报修管理」下面\n5. * 修改「报修管理」：介绍：报修全流程")
        self.assertEqual(kind, "ops")
        self.assertEqual([o["op"] for o in O.parse_ops(body)], ["add", "remove", "rename", "rename", "move", "set"])

    def test_系统自动和别的端做的动作不要求按钮(self):
        from backend import arch_ops as O
        arch = A.normalize({"nodes": [{"type": "page", "name": "报修工单", "children": [{"type": "button", "name": "派单", "action": "run"}]}]})
        arch["spec"] = {"roles": [{"name": "客服"}, {"name": "维修工"}], "objects": [{"name": "报修工单", "actions": [
            "派单：待派单→处理中（客服）", "超时升级：处理中→已超时（系统自动）", "报修：→待派单（业主，小程序）", "评价：待评价→已完成（业主）",
            "完工：处理中→待评价（维修工）", "关闭：待派单→已关闭"]}], "scope": {"out": ["业主小程序"]}}
        self.assertEqual(O.problems(arch), ["「报修工单」的「完工」这个动作没有按钮", "「报修工单」的「关闭」这个动作没有按钮"])

    def test_确认时问题定下来_生成原型时带上梳理(self):
        from backend import arch_spec as S
        spec = S.normalize({"roles": [{"name": "客服"}], "objects": [{"name": "工单", "states": ["待派单", "处理中"]}], "rules": ["紧急 30 分钟内派单"],
                            "questions": [{"q": "维修工要登录后台吗？", "options": ["要", "不要"]}, {"q": "费用要结算吗？", "options": ["只记录", "要结算"]}]})
        done = S.settle(spec, "按业务梳理画架构\n问题回答：\n- 维修工要登录后台吗？：不要")
        self.assertEqual(done["questions"], [])
        self.assertIn("维修工要登录后台吗？——不要", done["assumptions"])
        self.assertIn("费用要结算吗？——只记录（按推荐）", done["assumptions"])
        brief = A.brief(A.normalize({"nodes": [{"type": "page", "name": "工单"}], "spec": {**done, "status": "confirmed"}}))
        self.assertIn("紧急 30 分钟内派单", brief)
        self.assertIn("状态流转用 Store.flow 写", brief)
        self.assertNotIn("业务梳理", A.brief(A.normalize({"nodes": [{"type": "page", "name": "工单"}], "spec": spec})))   # 草稿不带

    def test_截断了说出来_还能接着画(self):
        from backend import arch_chat as C
        summary, nodes, notes = C._apply_reply({"nodes": []}, "说明：画了。\n\n【页面】\n报修管理 [模块]\n  报修工单 [菜单页]\n  维修工管", {"finish_reason": "length"})
        self.assertEqual([n["name"] for n in nodes[0]["children"]], ["报修工单"])          # 半截的最后一行不要
        self.assertIn(C.TRUNCATED, notes)
        self.assertEqual(C._limit(C.MAX_TOKENS, 65536), 65536)                               # 设置里调大了就用设置的


class 改动看不懂不能换掉整棵树(unittest.TestCase):
    def test_改动一条都没看懂_或者回的树少了一大半_画布不动(self):
        from backend.arch_chat import _apply_reply
        from backend.errors import WorkError
        kids = [{"id": f"p{i}", "type": "page", "name": f"页{i}", "children": []} for i in range(14)]
        current = {"nodes": [{"id": "m", "type": "module", "name": "工单", "children": kids}]}
        with self.assertRaises(WorkError):    # 以前这几行被读成四个模块，整棵树被换掉
            _apply_reply(current, "【改动】\n- 把最外层那几个「筛选」都处理一下\n- 还有分类列表", {})
        with self.assertRaises(WorkError):
            _apply_reply(current, "模块：删掉的东西\n  菜单页：页1", {})
        summary, nodes, _ = _apply_reply(current, "【改动】\n- 删掉最外层的「页3」", {})
        self.assertEqual(len(nodes[0]["children"]), 13)   # 「删掉最外层的「…」」也认


class 重放找不到位置的改动(unittest.TestCase):
    def test_挂的地方没了就跳过_不堆到最外层(self):
        from backend.arch_expand import replay
        tree = [{"id": "m1", "type": "module", "name": "基础设置", "children": []}]
        ops = [{"op": "add", "parent": "gone", "index": 0, "node": {"id": "x", "type": "table", "name": "分类列表", "children": []}},
               {"op": "add", "parent": "m1", "index": 0, "node": {"id": "y", "type": "page", "name": "材料价目", "children": []}}]
        out = replay(tree, ops)
        self.assertEqual([n["name"] for n in out], ["基础设置"])
        self.assertEqual([n["name"] for n in out[0]["children"]], ["材料价目"])


class 读列表页模板做的页面(unittest.TestCase):
    def test_页签不带数_同样的表只记一次_编号弹窗用按钮名(self):
        from backend.arch_expand import _fill
        table = '<div class="card-title">工单列表</div><table class="data-table"><thead><tr><th>工单编号</th><th>状态</th><th>操作</th></tr></thead><tbody><tr><td><button class="lnk">BX-001</button></td><td>待派单</td><td><button>派单</button></td></tr></tbody></table>'
        nodes = [{"id": 1, "parent": None, "label": "表格行 · 派单", "title": "派单 · BX-001", "html": '<section role="dialog" aria-label="派单 · BX-001"><label>维修工</label><select></select></section>'},
                 {"id": 2, "parent": None, "label": "页签 · 待接单2", "kind": "subpage", "title": "待接单2", "html": table.replace("派单</button>", "接单</button>")},
                 {"id": 3, "parent": 2, "label": "表格行 · 接单", "title": "确认接单", "html": '<section role="dialog" aria-label="确认接单"></section>'}]
        page = {"type": "page", "name": "工单管理", "children": []}
        _fill(page, table, nodes, None, {None: [("表格行 · BX-001", "jump", "工单详情页")]})
        kids = page["children"]
        tab = next(k for k in kids if k["type"] == "tab")
        self.assertEqual((tab["name"], tab["children"]), ("待接单", []))          # 页签只留名字
        buttons = [b["name"] for b in next(k for k in kids if k["type"] == "table")["children"]]
        self.assertEqual(buttons, ["派单", "接单", "工单编号"])                     # 接单并到页面的表上；编号按列名记一次
        self.assertIn("派单", [k["name"] for k in kids if k["type"] == "modal"])      # 不叫 BX-001
        self.assertIn("确认接单", [k["name"] for k in kids if k["type"] == "modal"])


class 谁做的动作(unittest.TestCase):
    def test_括号第一段是谁_后面是说明(self):
        from backend.arch_ops import _needs_button
        self.assertTrue(_needs_button("关闭：待派单→已关闭（客服，需填原因；超时的标红）", ["物业客服", "维修工"]))
        self.assertFalse(_needs_button("评价：待评价→已完成（业主在小程序评价后自动更新）", ["物业客服"]))
        self.assertFalse(_needs_button("超时升级：待派单→待派单（系统）", ["物业客服"]))


class 第一轮真实测试的毛病(unittest.TestCase):
    def test_检查带完整路径_还查空下钻页_没动作的按钮_占位模块(self):
        from backend import arch_ops as O
        arch = A.normalize({"nodes": [
            {"type": "module", "name": "业务模块", "children": [{"type": "page", "name": "首页", "desc": "工作台"}]},
            {"type": "module", "name": "能碳管理", "children": [
                {"type": "page", "name": "减排措施", "children": [{"type": "tab", "name": "已登记", "children": [{"type": "table", "name": "列表"}]}]},
                {"type": "page", "name": "能碳看板", "children": [{"type": "button", "name": "下钻", "action": "jump", "target": "企业碳排明细"},
                                                               {"type": "drill", "name": "企业碳排明细"}]}]},
            {"type": "module", "name": "告警运维", "children": [
                {"type": "page", "name": "告警监测", "children": [{"type": "button", "name": "去处理", "action": "jump", "target": "告警工单 / 待派单"},
                                                              {"type": "button", "name": "启停"}, {"type": "button", "name": "查询"}]},
                {"type": "page", "name": "告警工单", "children": [{"type": "tab", "name": "待派单"}]}]}]})
        found = O.problems(arch)
        self.assertIn("「能碳管理 / 减排措施 / 已登记 / 列表」这个表格叫「列表」，起个具体的名字", found)
        self.assertIn("下钻页「能碳管理 / 能碳看板 / 企业碳排明细」下面是空的：写清它展示什么", found)
        self.assertTrue(any("没写从哪进来" in p for p in found))
        self.assertTrue(any("按钮「告警运维 / 告警监测 / 启停」没写点了以后" in p for p in found))
        self.assertFalse(any("查询" in p for p in found))                                  # 查询这种不用写
        self.assertTrue(any("「业务模块」是页面外壳自带的占位名" in p for p in found))
        self.assertFalse(any("告警工单 / 待派单" in p for p in found))                       # 跳到「页面 / 页签」认得
        self.assertFalse(any("待派单" in p and "空" in p for p in found))                    # 页签只列名字是对的

    def test_梳理卡_选项里的推荐_假设里的问题编号去掉(self):
        from backend import arch_spec as S
        spec = S.normalize({"roles": [{"name": "管理员"}], "assumptions": ["企业用户共用后台（由问题1确认）。", "数据只接收。"],
                            "questions": [{"q": "企业用户怎么访问？", "options": ["同一后台（推荐）", "单独门户", "推荐"]}]})
        self.assertEqual(spec["questions"][0]["options"], ["同一后台", "单独门户"])
        self.assertEqual(spec["assumptions"], ["企业用户共用后台", "数据只接收"])

    def test_问架构合不合理_带上规则和检查结果(self):
        from backend import arch_chat as C
        self.assertIn("对照下面这些产品规则逐条看", C.ASK_SYSTEM)
        self.assertIn("不要每个页签重复一套筛选", C.ASK_SYSTEM)


class 表格起名(unittest.TestCase):
    def test_一页几张表各读各的_按卡片标题起名(self):
        html = ('<div class="metric-card"><div class="metric-title">今日用电量</div><b>1,200</b></div>'
                '<div class="card"><div class="card-title">日运行明细</div><div class="card-desc">用电、光伏与碳排</div>'
                '<table><tr><th>日期</th><th>用电量</th></tr><tr><td>10-26</td><td>1,200</td></tr></table></div>'
                '<div class="card"><div class="card-title">设备状态</div><table><tr><th>设备编号</th><th>状态</th><th>操作</th></tr>'
                '<tr><td>EQ-01</td><td>告警</td><td><button>处理</button></td></tr></table></div>')
        nodes = [{"id": 1, "parent": None, "label": "表格行 · 处理", "title": "告警详情", "layerSel": "#drawer", "html": "<dt>告警编号</dt>"}]
        page = {"type": "page", "name": "园区驾驶舱", "children": []}
        D._fill(page, html, nodes, None)
        tables = {c["name"]: c for c in page["children"] if c["type"] == "table"}
        self.assertEqual(list(tables), ["日运行明细", "设备状态"])
        self.assertEqual(tables["日运行明细"]["cols"], ["日期", "用电量"])               # 列不再混在一起
        self.assertEqual([b["name"] for b in tables["设备状态"]["children"]], ["处理"])   # 行按钮挂在它那张表下面

    def test_没标题的几张表_页面名加列表_不重名(self):
        html = "<table><tr><th>告警编号</th></tr></table><table><tr><th>规则名称</th></tr></table>"
        names = [t["name"] for t in D._tables(html, "实时告警")]
        self.assertEqual(names[0], "实时告警列表")
        self.assertEqual(len(set(names)), 2)

    def test_老画布上的列表_按列对上新名字_不算删了又加(self):
        canvas = [{"id": "p1", "type": "page", "name": "实时告警", "proto": True, "seen": True, "children": [
            {"id": "t1", "type": "table", "name": "列表", "cols": ["告警编号", "等级", "状态"], "proto": True, "seen": True, "desc": "我写的介绍", "children": []}]}]
        fresh = [{"type": "page", "name": "实时告警", "children": [
            {"type": "table", "name": "实时告警列表", "cols": ["告警编号", "等级", "状态", "发生时间"], "children": []}]}]
        tree, base = D.refresh_canvas(canvas, copy.deepcopy(canvas), fresh)
        table = tree[0]["children"]
        self.assertEqual(len(table), 1)                                  # 没有多出一张「原型里已经没有」的列表
        self.assertEqual((table[0]["id"], table[0]["name"]), ("t1", "实时告警列表"))
        self.assertEqual(table[0]["desc"], "我写的介绍")


class 从原型读得更全(unittest.TestCase):
    def test_没弹出东西的按钮也记下(self):
        result = {"page": "<table><tr><th>设备编号</th><th>状态</th></tr></table>",
                  "nodes": [{"id": 1, "parent": None, "label": "表格行 · 查看", "title": "1#光伏逆变器 · 设备详情", "layerSel": "#activeDrawer",
                             "html": '<section role="dialog" aria-label="1#光伏逆变器 · 设备详情"><dt>设备编号</dt></section>'},
                            {"id": 2, "parent": None, "label": "派单处理", "title": "派单", "layerSel": "#activeModal",
                             "html": '<section role="dialog" aria-label="派单"><label>处理人</label><button>确认派单</button></section>'}],
                  "jumps": [{"parent": None, "label": "查看全部告警", "hash": "#live"}],
                  "dead": [{"parent": None, "label": "导出日报"}],
                  "coverage": {"none": {"n": 1, "labels": ["确认派单"]}, "skipped": {"commit": {"n": 1, "labels": ["停用"]}, "noise": {"n": 2, "labels": ["查询", "导出清单"]}}}}
        page = {"type": "page", "name": "设备运行状态", "children": []}
        D._fill(page, result["page"], result["nodes"], None, D._extras(result, {"#live": "实时告警"}))
        flat = {n["name"]: n for n, _, _ in D._walk([page])}
        self.assertIn("设备详情", flat)                                           # 标题只留后半截
        self.assertEqual((flat["查看全部告警"]["action"], flat["查看全部告警"]["target"]), ("jump", "实时告警"))
        self.assertEqual(flat["停用"]["action"], "confirm")
        self.assertEqual(flat["导出清单"]["action"], "run")
        self.assertNotIn("查询", flat)
        self.assertIn("确认派单", [c["name"] for c in flat["派单"]["children"]])   # 弹窗里的按钮挂在弹窗下面
        self.assertEqual(flat["导出日报"]["target"], "点了还没反应")

    def test_架构模式的AI看得到原型代码里的线索(self):
        from backend.arch_chat import prototype_digest
        src = "<script>\n" + "\n".join(["const Pages={", "user:()=>Btn({label:'新增账号'})+'角色权限',", "param:()=>'修改参数'+'变更原因',", "};"]) + "\n" + "//" * 300 + "\n</script>"
        text = prototype_digest(src)
        self.assertIn("代码地图", text)
        self.assertIn("新增账号", text)
        self.assertLess(len(text), 15_000)
