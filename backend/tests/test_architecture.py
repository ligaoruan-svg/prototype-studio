"""架构模式：收拾数据、检查对不对得上、按依赖排生成顺序、交给 AI 的文字、接口、按架构生成时放进背景"""
import sys
import tempfile
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
        self.assertIn(("block", "筛选 / 表单"), kinds)
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


class 功能清单(unittest.TestCase):
    def test_有表头_合并单元格沿用上一行(self):
        text = "编号\t模块\t菜单\t功能\t功能描述\n85\t设备管理\t设备定义\t新增定义\t定义参数模板\n86\t\t设备录入\t新增录入\t4 步向导\n87\t\t\t批量导入\t下载模板\n88\t巡检\t巡检计划\t新增计划\t"
        self.assertTrue(T.looks_like_table(text))
        arch = A.normalize(T.from_table(text))
        top = arch["nodes"]
        self.assertEqual([n["name"] for n in top], ["设备管理", "巡检"])
        entry = top[0]["children"][1]
        self.assertEqual(entry["name"], "设备录入")
        self.assertEqual([c["name"] for c in entry["children"]], ["新增录入", "批量导入"])
        self.assertEqual(entry["children"][1]["req"], ["87"])
        self.assertEqual(entry["children"][0]["desc"], "4 步向导")

    def test_没表头也能认(self):
        arch = A.normalize(T.from_table("设备管理\t设备定义\t新增定义\n\t\t编辑定义"))
        self.assertEqual(len(arch["nodes"][0]["children"][0]["children"]), 2)

    def test_追加时同名的并到一起(self):
        target = [{"name": "设备管理", "children": [{"name": "设备定义", "children": []}]}]
        T.merge_nodes(target, [{"name": "设备管理", "children": [{"name": "设备定义", "desc": "模板", "children": [{"name": "新增"}]}, {"name": "设备录入"}]}])
        self.assertEqual(len(target), 1)
        self.assertEqual([c["name"] for c in target[0]["children"]], ["设备定义", "设备录入"])
        self.assertEqual(target[0]["children"][0]["desc"], "模板")


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

    def test_大纲和粘贴(self):
        r = self.c.post(f'/api/projects/{self.pid}/architecture/outline', json={'text': '设备管理\n  设备定义'})
        self.assertEqual(r.json()['counts']['pages'], 1)
        r = self.c.post(f'/api/projects/{self.pid}/architecture/import', json={'text': '模块\t菜单\t功能\n设备管理\t设备录入\t批量导入', 'mode': 'append'})
        self.assertEqual(r.json()['counts']['pages'], 2)          # 设备管理并到一起，多了设备录入
        self.assertEqual(r.json()['counts']['modules'], 1)
        r = self.c.post(f'/api/projects/{self.pid}/architecture/import', json={'text': '巡检\n  计划', 'mode': 'replace'})
        self.assertEqual(r.json()['counts']['pages'], 1)
        self.assertEqual(self.c.post(f'/api/projects/{self.pid}/architecture/import', json={'text': ''}).status_code, 400)

    def test_从原型读_有没同步的改动就先不读(self):
        page = storage.load_meta(self.pid)['pages'][0]['id']
        url = f'/api/projects/{self.pid}/architecture'
        r = self.c.post(url + '/refresh', json={})
        self.assertEqual(r.json()['reason'], 'no_expand')               # 没展开过：什么都不动
        storage.save_expand_routes(self.pid, page, [{'hash': '#order', 'title': '报修工单'}, {'hash': '#test', 'title': '测试'}])
        storage.save_expand_entry(self.pid, page, '#order', 'h', {'page': '<table><tr><th>工单号</th></tr></table>', 'nodes': []})
        r = self.c.post(url + '/refresh', json={}).json()
        self.assertTrue(r['refreshed'])
        self.assertEqual([n['name'] for n in r['architecture']['nodes']], ['报修工单', '测试'])   # 没分组的菜单项放最外层
        self.assertEqual(r['synced'], r['architecture']['nodes'])
        # 在树里写了介绍、加了一页：还没同步，重读不会冲掉
        arch = r['architecture']
        arch['nodes'][0]['desc'] = '接单派单'
        arch['nodes'].append({'type': 'page', 'name': '维修工'})
        self.c.put(url, json={'architecture': arch})
        self.assertEqual(self.c.post(url + '/refresh', json={}).json()['reason'], 'pending')
        # 同步完了：再读，原型里没有的那一页去掉，介绍留着
        self.c.post(url + '/synced')
        r = self.c.post(url + '/refresh', json={}).json()
        self.assertEqual([n['name'] for n in r['architecture']['nodes']], ['报修工单', '测试'])
        self.assertEqual(r['architecture']['nodes'][0]['desc'], '接单派单')
        self.assertEqual(r['architecture']['nodes'][0]['id'], arch['nodes'][0]['id'])

if __name__ == '__main__':
    unittest.main()


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
