"""错误卡片的文案。

标题要能让用户知道下一步干什么；详情是给排查用的原文。
两者相同的时候不能都显示——卡片把同一句话印两遍，看着像坏了。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.errors import WorkError, error_payload   # noqa: E402


class Payload(unittest.TestCase):
    def test_标题和详情不重复(self):
        for code in ('stalled', 'tool_rejected', 'iterations', 'patch_target',
                     'validation', 'output_limit', 'invalid_arguments', 'internal'):
            with self.subTest(code=code):
                got = error_payload(WorkError(code, "某个很长的内部原因，当前文件未改动"))
                if got["detail"]:
                    self.assertNotEqual(got["message"], got["detail"])

    def test_没登记的错误码只给一句(self):
        """以前会回退成 detail，于是标题和详情是同一句话。"""
        got = error_payload(WorkError("zzz_brand_new", "某个没见过的新错误"))
        self.assertEqual(got["message"], "某个没见过的新错误")
        self.assertEqual(got["detail"], "", "没有额外信息时就别展开「查看详情」")

    def test_守卫的错误码都登记了(self):
        """agent 里 raise 出来的每个 code 都要有给用户看的话。"""
        agent = (Path(__file__).resolve().parents[2] / "backend" / "agent.py").read_text("utf-8")
        import re
        codes = set(re.findall(r'incomplete = \("(\w+)"', agent))
        codes |= set(re.findall(r'WorkError\("(\w+)"', agent))
        for code in codes:
            with self.subTest(code=code):
                got = error_payload(WorkError(code, "原因"))
                self.assertTrue(got["detail"], f"{code} 没登记标题，会把原因当标题印两遍")

    def test_标题要说清下一步(self):
        for code in ('stalled', 'tool_rejected'):
            with self.subTest(code=code):
                message = error_payload(WorkError(code, "x"))["message"]
                self.assertTrue(any(w in message for w in ("点选", "框选", "重试", "缩小", "换")),
                                "错误卡片得告诉用户能做什么，不能只报告失败")


if __name__ == "__main__":
    unittest.main()


class StepDetail(unittest.TestCase):
    """每一步做完要说清拿到了什么。

    只给个标签「查找「overview」」，用户看不出搜到没搜到——
    卡住的时候只能干等，这是最折磨人的地方。
    """

    def setUp(self):
        from backend.experience import step_detail
        self.detail = step_detail

    def test_搜到了说找到几处在哪几行(self):
        got = self.detail("search_source", {"query": "总览"}, {"hits": 19, "lines": [53, 216, 749]})
        self.assertIn("19 处", got)
        self.assertIn("53", got)

    def test_没搜到要说没搜到(self):
        got = self.detail("search_source", {"query": "overview"}, {"hits": 0, "context": "整个页面里没有"})
        self.assertIn("没有找到", got)
        self.assertIn("overview", got)

    def test_读代码说清读到哪还剩多少(self):
        got = self.detail("read_source_slice", {}, {"start": 1, "end": 155, "total_lines": 6671, "truncated": True})
        self.assertIn("1–155", got)
        self.assertIn("6671", got)
        self.assertIn("还没读完", got)

    def test_失败要给原因(self):
        got = self.detail("apply_operations", {}, {"ok": False, "error": "没有找到要替换的原文"})
        self.assertIn("没有找到要替换的原文", got)

    def test_校验通过与不通过都说清(self):
        self.assertIn("通过", self.detail("verify_page", {}, {"ok": True, "issues": []}))
        self.assertIn("data-pid", self.detail("verify_page", {}, {"issues": ["data-pid 不能重复"]}))

    def test_每条都短得下得了一行(self):
        long_out = {"hits": 900, "lines": list(range(900))}
        self.assertLessEqual(len(self.detail("search_source", {"query": "x"}, long_out)), 320)
        self.assertLessEqual(len(self.detail("whatever", {}, {"a": "x" * 5000})), 320)

    def test_没见过的工具也不炸(self):
        for out in (None, "纯文字", 123, {"随便": "什么"}):
            with self.subTest(out=out):
                self.assertIsInstance(self.detail("unknown_tool", {}, out), str)
