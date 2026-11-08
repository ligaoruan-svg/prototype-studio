"""架构模式边写边给人看：回答一句句出来，梳理 / 清单一块块亮（以前只有「已写 802 字」）"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.arch_live import Live, rows, visible   # noqa: E402

SAMPLE = json.loads((Path(__file__).parent / "arch_samples/物业报修.json").read_text("utf-8"))


class 边写边看(unittest.TestCase):
    def test_回答只吐正文_建议留给卡片(self):
        text = "结构清楚，有两处可以更好。\n\n可以这样改：\n- 标红｜一眼看到｜超时行标红"
        self.assertEqual(visible("ask", text), "结构清楚，有两处可以更好。")
        self.assertEqual(visible("edit", "加了催办记录页。\n【改动】\n+ 报修工单 / 催办记录"), "加了催办记录页。")
        self.assertEqual(visible("plan", '{"modules":'), "")

    def test_梳理写到哪亮到哪(self):
        text = json.dumps(SAMPLE["spec"], ensure_ascii=False)
        half = text[:text.index('"flows"') + 12]
        got = rows("spec", half)
        self.assertEqual([r[0] for r in got], ["live-roles", "live-objects", "live-flows"])
        self.assertEqual(got[0][1], "角色：物业客服、维修工、物业主管、业主")
        self.assertTrue(got[1][1].startswith("业务对象：报修工单、工单材料明细"))
        self.assertTrue(visible("spec", half).startswith("面向物业公司"))

    def test_清单按模块列页面(self):
        text = json.dumps(SAMPLE["plan"], ensure_ascii=False)
        got = dict(rows("plan", text))
        self.assertEqual(got["live-m0"], "首页：首页（看板）")
        self.assertEqual(got["live-m1"], "报修工单：工单管理（管理列表）、我的任务（我的任务）、催办记录（管理列表）")

    def test_事件_写完的打勾_正在写的转圈(self):
        events = []
        live = Live("ask", events.append)
        for piece in ["结构", "清楚。", "\n\n可以这样改：\n- a｜b｜c"]:
            live.feed(piece)
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "text_delta"), "结构清楚。")
        events.clear()
        live = Live("plan", events.append)
        text = json.dumps(SAMPLE["plan"], ensure_ascii=False)
        for i in range(0, len(text), 50):
            live.feed(text[i:i + 50])
        live.finish()
        last = {e["id"]: e["state"] for e in events if e["type"] == "live"}
        self.assertTrue(last and all(s == "done" for s in last.values()))
        self.assertIn("running", [e["state"] for e in events if e["type"] == "live"])


class 推理模型想的过程(unittest.TestCase):
    def test_reasoning_content_推给界面(self):
        from backend.deepseek_client import _assemble
        got = []
        events = [{"choices": [{"delta": {"reasoning_content": "用户想讨论"}}]}, {"choices": [{"delta": {"reasoning": "，不改"}}]},
                  {"choices": [{"delta": {"content": "好的"}, "finish_reason": "stop"}]}]
        out = _assemble(events, lambda text, kind: got.append((kind, text)))
        self.assertEqual(got, [("think", "用户想讨论"), ("think", "，不改"), ("note", "好的")])
        self.assertEqual(out["choices"][0]["message"]["content"], "好的")       # 想的不进回复
