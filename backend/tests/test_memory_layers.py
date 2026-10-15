"""记忆参照 Claude：两层（这个项目 / 所有项目）、按类别、暂停、清空、一句话改、后台自己整理。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, memory   # noqa: E402


class 两层记忆(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name) / "projects"
        storage.DATA_ROOT.mkdir(parents=True)
        self.a = storage.create_project("甲")["id"]
        self.b = storage.create_project("乙")["id"]

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def test_项目的只在本项目_个人习惯每个项目都带(self):
        memory.add(self.a, "表单标签右对齐", "设计风格", "project")
        memory.add(self.a, "回复简短一点，先说结论", "协作方式", "global")
        block_b = memory.index_block(storage.load_meta(self.b))
        self.assertIn("回复简短一点", block_b)
        self.assertNotIn("表单标签右对齐", block_b)
        block_a = memory.index_block(storage.load_meta(self.a))
        self.assertIn("设计风格：", block_a)
        self.assertIn("表单标签右对齐", block_a)

    def test_旧数据补上类别和来源(self):
        meta = storage.load_meta(self.a)
        meta["memory"] = [{"id": "m1", "text": "表格都带斑马纹", "created_at": "x"}]
        storage.save_meta(meta)
        item = memory.snapshot(self.a)["project"]["memory"][0]
        self.assertEqual((item["category"], item["source"]), ("设计风格", "said"))

    def test_改_删_暂停_清空(self):
        saved = memory.add(self.a, "按钮一律用描边", "设计风格")
        memory.update(self.a, saved["id"], "次要按钮用描边，主按钮实心")
        self.assertEqual(memory.snapshot(self.a)["project"]["memory"][0]["text"], "次要按钮用描边，主按钮实心")
        memory.set_paused(self.a, "project", True)
        self.assertTrue(memory.paused(self.a))
        self.assertIn("暂停了记忆", memory.index_block(storage.load_meta(self.a)))
        memory.clear(self.a, "project")
        self.assertEqual(memory.snapshot(self.a)["project"]["memory"], [])

    def test_一句话改记忆(self):
        saved = memory.add(self.a, "按钮一律用描边", "设计风格")
        llm = lambda prompt: json.dumps({"update": [{"id": saved["id"], "text": "只有次要按钮用描边"}],
                                         "add": [{"text": "配额指年度免费排放额度", "category": "业务与术语"}], "remove": []}, ensure_ascii=False)
        done = memory.edit_by_instruction(self.a, "描边只对次要按钮，再记一下配额是什么", llm)
        self.assertEqual(len(done["updated"]), 1)
        texts = [e["text"] for e in memory.snapshot(self.a)["project"]["memory"]]
        self.assertIn("只有次要按钮用描边", texts)
        self.assertIn("配额指年度免费排放额度", texts)

    def test_攒够几条才整理_整理过的不重复整理(self):
        for i in range(3):
            storage.append_chat(self.a, "user", f"把第 {i} 个按钮改成描边")
        calls = []
        llm = lambda prompt: calls.append(prompt) or json.dumps({"add": [{"text": "按钮偏好描边样式", "category": "设计风格"}]}, ensure_ascii=False)
        self.assertEqual(memory.synthesize(self.a, llm).get("skipped"), "not_enough")
        storage.append_chat(self.a, "user", "这个也改成描边")
        done = memory.synthesize(self.a, llm)
        self.assertEqual([e["text"] for e in done["added"]], ["按钮偏好描边样式"])
        self.assertEqual(memory.snapshot(self.a)["project"]["memory"][0]["source"], "auto")
        self.assertIn("这个也改成描边", calls[0])
        self.assertEqual(memory.synthesize(self.a, llm).get("skipped"), "not_enough", "整理过的发言不再算")

    def test_模型乱回不出事(self):
        for i in range(4):
            storage.append_chat(self.a, "user", f"第 {i} 句")
        done = memory.synthesize(self.a, lambda p: "我觉得没什么要记的")
        self.assertEqual(done, {"added": [], "updated": [], "removed": []})
        with self.assertRaises(ValueError):
            memory.edit_by_instruction(self.a, "随便改改", lambda p: "好的")

    def test_以前的对话查得到_超过四十条也在(self):
        for i in range(45):
            storage.append_chat(self.a, "user", f"第 {i} 句：主色用 #1f6feb" if i == 2 else f"第 {i} 句")
        self.assertEqual(len(storage.load_meta(self.a)["chat"]), 40)
        hits = storage.search_chat_log(self.a, "主色")
        self.assertEqual(len(hits), 1)
        self.assertIn("#1f6feb", hits[0]["content"])


if __name__ == "__main__":
    unittest.main()
