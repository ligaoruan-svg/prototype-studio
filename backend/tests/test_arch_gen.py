"""3C 画布 → 页面：带表格的菜单页程序直接写成 ListPage 配置，AI 只补演示数据、手写页和规则"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import agent, architecture, arch_gen, skill_digest, storage   # noqa: E402

SPEC = {"status": "confirmed", "roles": [{"name": "物业客服"}, {"name": "维修工"}],
        "objects": [{"name": "报修工单", "states": ["待派单", "待接单", "已关闭"],
                     "actions": ["派单：待派单→待接单（客服，选维修工）", "关闭：待派单→已关闭（客服，填原因）", "超时：待派单→待派单（系统）"]}]}
TREE = [{"type": "module", "name": "报修工单", "children": [
    {"type": "page", "name": "工单管理", "route": "workorder", "children": [
        {"type": "tab", "name": "待派单"}, {"type": "tab", "name": "待接单"},
        {"type": "block", "name": "筛选", "fields": ["工单编号", "报修分类（下拉：水电/门窗）", "状态（下拉：待派单/待接单）", "提交时间起（日期）", "提交时间止（日期）"]},
        {"type": "table", "name": "工单列表", "cols": ["工单编号", "报修分类", "状态", "材料费"], "children": [
            {"type": "button", "name": "派单", "action": "open", "target": "派单", "when": "状态是待派单时"},
            {"type": "button", "name": "关闭", "action": "open", "target": "关闭工单", "when": "状态是待派单时"},
            {"type": "button", "name": "查看", "action": "open", "target": "工单详情"},
            {"type": "button", "name": "BX-001", "action": "jump", "target": "工单详情页"}]},
        {"type": "modal", "name": "派单", "fields": ["维修工*（下拉）", "派单说明（多行）"]},
        {"type": "modal", "name": "关闭工单", "fields": ["关闭原因*（多行）", "工单编号🔒"]},
        {"type": "drawer", "name": "工单详情", "fields": ["工单编号", "状态", "评价内容（数据：小程序回传）"]},
        {"type": "button", "name": "新增工单", "action": "open", "target": "新增工单"},
        {"type": "modal", "name": "新增工单", "fields": ["工单编号*", "报修分类*（下拉：水电/门窗）"]}]},
    {"type": "page", "name": "工单统计", "children": [{"type": "block", "name": "指标卡", "fields": ["今日新增"]}]}]}]


class 画布直接生成列表页(unittest.TestCase):
    def test_一页配置照画布写(self):
        gen = arch_gen.generate({"nodes": TREE, "spec": SPEC})
        self.assertEqual((gen["made"], gen["left"]), (["工单管理"], ["工单统计"]))   # 有指标卡的看板留给 AI
        page = gen["pages"]
        for want in ['data:"报修工单"', 'tabs:["待派单","待接单"]', 'type:"daterange"', 'key:"status",label:"状态",tag:true',
                     'money:true', '{label:"派单",flow:"派单",form:[{key:"维修工",label:"维修工",type:"select",options:()=>[...new Set(Store.all("报修工单")',
                     'required:true', 'title:"关闭工单"', '{label:"查看",detail:true}', 'readonly:true',
                     '{label:"新增工单",form:', 'add:true', 'defaults:{status:"待派单"}', '{key:"评价内容",label:"评价内容"}']:
            self.assertIn(want, page)
        self.assertNotIn('label:"状态",type:"select"', page)      # 有页签就不要「状态」筛选
        self.assertNotIn("BX-001", page)                            # 编号跳详情页留给 AI
        self.assertIn('Store.flow("报修工单",{"派单":["待派单","待接单"],"关闭":["待派单","已关闭"]', gen["script"])
        self.assertIn("工单统计（key: p2）", arch_gen.handoff(gen))
        dashed = arch_gen.generate({"nodes": [{**TREE[0], "children": [{**TREE[0]["children"][0], "route": "order-fee"}]}], "spec": SPEC})
        self.assertTrue(dashed["pages"].startswith('"order-fee"(){return ListPage('))   # 带 - 的页面名加引号，不然整页脚本报错

    def test_起点是空的动作_做成顶上的新增按钮(self):
        spec = {"status": "confirmed", "roles": [{"name": "财务对账员"}], "objects": [{"name": "月度对账单", "states": ["待核对", "已对平"],
                "actions": ["生成：—→待核对（财务对账员）", "对平：待核对→已对平（财务对账员）"]}]}
        tree = [{"type": "page", "name": "月度对账单", "children": [
            {"type": "table", "name": "对账单列表", "cols": ["账期月份", "状态"], "children": []},
            {"type": "button", "name": "生成对账单", "action": "open", "target": "生成对账单"},
            {"type": "modal", "name": "生成对账单", "fields": ["账期月份*（下拉：2026-10/2026-11）"]}]}]
        gen = arch_gen.generate({"nodes": tree, "spec": spec})
        self.assertIn('add:true,primary:true,defaults:{status:"待核对"}', gen["pages"])
        self.assertNotIn('"生成"', gen["script"])             # 新建不是流转

    def test_演示数据也照配置生成(self):
        gen = arch_gen.generate({"nodes": TREE, "spec": SPEC})
        script = gen["script"]
        self.assertIn('Store.define("报修工单",[', script)
        for want in ['status:"待派单"', 'status:"待接单"', 'status:"已关闭"', '"工单编号":"WO20261101"', '"报修分类":"水电"', '"材料费":60',
                     'Demo.at(', 'Demo.t("报修工单·派单说明",']:
            self.assertIn(want, script)
        self.assertIn("报修工单·派单说明", gen["texts"])            # 文字留给 AI 换成真话
        self.assertIn("别再 Store.define 同一份", arch_gen.handoff(gen))

    def test_同步到空外壳时程序先生成_再交给AI补(self):
        tmp = tempfile.TemporaryDirectory()
        old = storage.DATA_ROOT, agent.chat, agent.stage
        try:
            storage.DATA_ROOT = Path(tmp.name)
            pid = storage.create_project("t")["id"]
            meta = storage.load_meta(pid); meta["style"] = "builtin:企业蓝"; storage.save_meta(meta)
            shell = skill_digest.find_shell(meta)[2]
            (storage.project_dir(pid) / "source" / "index.html").write_text(shell, encoding="utf-8")
            page = storage.add_page(pid, "index.html")["id"]
            architecture.save(pid, {"name": "t", "nodes": TREE, "spec": SPEC})
            sent, staged = [], []
            agent.chat = lambda key, model, messages, tools, **k: (sent.append(messages), {"choices": [{"finish_reason": "tool_calls", "message": {
                "content": "", "tool_calls": [{"id": "c", "type": "function", "function": {"name": "report_result",
                                                "arguments": json.dumps({"summary": "好了", "annotations": []})}}]}}]})[1]
            agent.stage = lambda pid_, page_, before, after, *a, **k: (staged.append(after), {"pending_id": "x"})[1]
            agent.run_agent(pid, page, "按架构画布做页面", "k", "m", intent="edit", stream=False, architecture=True)
            self.assertIn("程序已经照画布把这些列表页写好了", sent[0][1]["content"])
            self.assertIn('workorder(){return ListPage({title:"工单管理"', staged[-1])
        finally:
            storage.DATA_ROOT, agent.chat, agent.stage = old
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
