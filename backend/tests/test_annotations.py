"""先记下的意见要带上所在弹窗。

展开视图里能一次记好几处、最后一次修改——但如果记下时丢了「在哪个弹窗里」，
AI 逐条处理时又只能满文件搜按钮文字，等于白记。
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage   # noqa: E402


class 记下的意见带上弹窗(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        meta = storage.create_project("测试")
        self.pid = meta["id"]
        src = storage.project_dir(self.pid) / "source" / "index.html"
        src.write_text("<html><body><div id='modal'></div></body></html>", encoding="utf-8")
        self.page = storage.add_page(self.pid, "index.html")["id"]

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def test_弹窗里的意见保留弹窗名和打开路径(self):
        ann = storage.add_annotation(self.pid, self.page, {"selector": "#modal > p", "note": "改短一点",
                                                           "in_modal": "新增 GWP 值", "modal_trail": "新增因子 › 下一步 · GWP值"})
        self.assertEqual(ann["in_modal"], "新增 GWP 值")
        self.assertEqual(ann["modal_trail"], "新增因子 › 下一步 · GWP值")
        stored = storage.active_annotations(storage.load_meta(self.pid), self.page)
        self.assertEqual(stored[0]["in_modal"], "新增 GWP 值")

    def test_子页面和业务页面路由也记下(self):
        ann = storage.add_annotation(self.pid, self.page, {"selector": "body > div > button", "note": "改名",
                                                           "in_subpage": "TMP-BUILD-2026-V2", "view_route": "#template",
                                                           "modal_trail": "表格行 · TMP-BUILD-2026-V2"})
        self.assertEqual((ann["in_subpage"], ann["view_route"]), ("TMP-BUILD-2026-V2", "#template"))

    def test_页面上的意见不带弹窗字段也照常保存(self):
        ann = storage.add_annotation(self.pid, self.page, {"selector": "h1", "note": "标题加粗"})
        self.assertEqual(ann["in_modal"], "")


if __name__ == "__main__":
    unittest.main()
