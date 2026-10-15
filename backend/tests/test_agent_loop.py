"""agent 循环的空转防护。

真实场景：用户要"给所有表格数字加千分位"，页面上其实一个四位数都没有。
旧循环连着读了 5 次源码、又去搜提示词举例里的「1500」，12 轮全烧光、25 万 tokens，
最后报"已达到轮次上限"。这里用一个只会读的假模型复现那种行为，验证防护生效。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.agent import _slice_lines, _search_source, read_budget, IDLE_LIMIT   # noqa: E402

PAGE_LINES = [f"<tr><td>行 {i}</td><td class='num'>{i * 7}</td></tr>" for i in range(400)]


class SliceHonesty(unittest.TestCase):
    def test_超出预算时说明真实到达的行号(self):
        out = _slice_lines(PAGE_LINES, 1, len(PAGE_LINES))
        self.assertTrue(out["truncated"])
        self.assertLess(out["end"], len(PAGE_LINES), "截断了就不能再报成读到末行")
        self.assertEqual(out["total_lines"], len(PAGE_LINES))
        self.assertIn(f"start={out['end'] + 1}", out["note"])
        # 返回的最后一行，就是它声称到达的那一行
        self.assertTrue(out["content"].splitlines()[-1].startswith(f"{out['end']}: "))

    def test_内容不超预算(self):
        self.assertLessEqual(len(_slice_lines(PAGE_LINES, 1, 400)["content"]), 12_000)

    def test_读取预算跟着上下文预算走(self):
        """窗口大就一次多给点，但绝不让一次读取吃掉超过四分之一的上下文。"""
        self.assertEqual(read_budget(40_000), 12_000, "窗口小也要保底能读一段")
        self.assertEqual(read_budget(200_000), 20_000, "一次最多读两万字，读进来的每步都要重发")
        self.assertEqual(read_budget(800_000), 20_000)
        for ctx in (40_000, 200_000, 800_000):
            self.assertLessEqual(read_budget(ctx), max(12_000, ctx // 4))

    def test_顺着提示能读完整个文件(self):
        at, rounds = 1, 0
        while at <= len(PAGE_LINES) and rounds < 20:
            out = _slice_lines(PAGE_LINES, at, len(PAGE_LINES))
            self.assertGreaterEqual(out["end"], at, "每次都要往前推进，不能原地打转")
            at = out["end"] + 1
            rounds += 1
            if not out.get("truncated"):
                break
        self.assertGreater(at, len(PAGE_LINES), "应当能读到文件末尾")

    def test_范围没超预算时不报截断(self):
        out = _slice_lines(PAGE_LINES, 1, 20)
        self.assertNotIn("truncated", out)
        self.assertEqual(out["end"], 20)


class SearchHonesty(unittest.TestCase):
    def test_搜不到时明确说页面上没有(self):
        out = _search_source("\n".join(PAGE_LINES), "1500")
        self.assertEqual(out["hits"], 0)
        self.assertIn("没有", out["context"])
        self.assertIn("不要再换范围重读", out["context"])

    def test_命中很多时说清只展开了前几处(self):
        out = _search_source("\n".join(PAGE_LINES), "class='num'")
        self.assertEqual(out["hits"], len(PAGE_LINES))
        self.assertIn("共命中", out["note"])
        self.assertLessEqual(len(out["lines"]), 20)

    def test_空搜索词不报错(self):
        self.assertEqual(_search_source("abc", "")["hits"], 0)


class IdleGuard(unittest.TestCase):
    def test_阈值是个正数且不至于太宽松(self):
        self.assertTrue(1 <= IDLE_LIMIT <= 6, "太大就等于没有守卫，太小会打断正常的多次读取")

    def test_重复读取会被挡回并给出下一步(self):
        """同一个 (工具, 参数) 第二次出现，应当拿到 already_read 而不是重发一遍内容。"""
        source = ROOT / "backend" / "agent.py"
        text = source.read_text("utf-8")
        self.assertIn("already_read", text)
        self.assertIn("read_seen", text)
        # 挡回的话术要指向出路，而不只是说"不许读"
        self.assertIn("report_result", text.split("already_read")[1][:600])

    def test_空转到阈值时会催它二选一(self):
        text = (ROOT / "backend" / "agent.py").read_text("utf-8")
        self.assertIn("idle_rounds", text)
        block = text.split("idle_rounds >= IDLE_LIMIT")[1][:700]
        self.assertIn("report_result", block)
        self.assertIn("CSS", block)


class PromptGuidance(unittest.TestCase):
    def setUp(self):
        self.prompt = (ROOT / "prompts" / "agent-system.md").read_text("utf-8")

    def test_删掉了找不到就重新读(self):
        self.assertNotIn("找不到就重新读", self.prompt,
                         "这句话本身就是在教它空转")

    def test_给了无需改动的出口(self):
        self.assertIn("没有改动", self.prompt)
        self.assertIn("不是失败", self.prompt)

    def test_交代了同类批量改动走一条规则(self):
        self.assertIn("一条 CSS 规则", self.prompt)

    def test_提醒不要拿举例里的数字去搜(self):
        self.assertIn("举例", self.prompt)

    def test_提醒看不出效果时要说明(self):
        self.assertIn("看不出", self.prompt)


if __name__ == "__main__":
    unittest.main()
