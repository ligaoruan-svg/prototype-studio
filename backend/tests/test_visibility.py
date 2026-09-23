"""每一步都得说清它拿到了什么。

真实场景：用户问「这个页面设计呢如何」，卡片上连着七行「查找「factorTab」」，
每行只有一个勾，点不开也看不到结果——等了半分钟，不知道它查到没查到。
原因有两个：一是有的分支 emit 时漏了 detail，前端就不给折叠按钮；
二是浏览器缓存着旧界面文件（那一条在 server.py 的 always_revalidate 里治）。
这里守住第一条：步骤列表上能出现的工具，每一个都要给得出一句人话。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.experience import step_detail   # noqa: E402

AGENT_SRC = (ROOT / "backend" / "agent.py").read_text(encoding="utf-8")

# (工具名, 参数, 返回值) —— 照着 agent.py 里各工具真实的返回结构写
SAMPLES = [
    ("inspect_page", {}, {"title": "零碳园区", "chars": 943553, "regions": [1, 2], "actions": [1]}),
    ("search_source", {"query": "factorTab"}, {"hits": 20, "lines": [53, 216, 900]}),
    ("search_source", {"query": "overview"}, {"hits": 0, "lines": []}),
    ("read_source_slice", {}, {"start": 1, "end": 155, "total_lines": 6671, "truncated": True}),
    ("read_region", {"name": "侧边栏"}, {"content": "x" * 40}),
    ("read_component", {}, {"content": "y" * 12}),
    ("read_skill", {}, {"content": "z" * 30}),
    ("apply_operations", {}, {"logs": ["把按钮改小了一档"]}),
    ("verify_page", {}, {"issues": []}),
    ("update_plan", {}, {"steps": [{"title": "定位目标"}, {"title": "改样式"}]}),
    ("report_result", {}, {"report": {"summary": "改了两处"}}),
    ("remember", {}, {"text": "本项目按钮主色用蓝色"}),
    ("ask_user", {}, {"clarification": {"question": "改哪一处？"}}),
    ("answer_user", {}, {"discussion": {"answer": "信息密度偏低"}}),
]


class 每一步都说得出结果(unittest.TestCase):
    def test_各工具都给得出一句人话(self):
        for name, args, output in SAMPLES:
            with self.subTest(tool=name):
                detail = step_detail(name, args, output)
                self.assertTrue(detail.strip(), f"{name} 没给出任何结果说明，前端就没有可展开的内容")

    def test_失败也要说清楚(self):
        self.assertIn("没定位到", step_detail("apply_operations", {}, {"ok": False, "error": "没定位到目标"}))

    def test_搜不到时直说没找到(self):
        self.assertIn("没有找到", step_detail("search_source", {"query": "overview"}, {"hits": 0}))

    def test_每个_step_done_都带上_detail(self):
        """漏一个分支，那一行在界面上就没有折叠箭头，用户只能干看着工具名。"""
        for emit in re.findall(r'emit\(\{[^}]*"type":\s*"step_(?:error" if failed else "step_)?done[^}]*\}', AGENT_SRC):
            self.assertIn('"detail"', emit, f"这条 emit 漏了 detail：{emit[:120]}")


if __name__ == "__main__":
    unittest.main()
