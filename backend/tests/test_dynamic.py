"""从渲染出来的 DOM 反查拼出它的源码。

这是"只做修改"路线上最卡脖子的一环：用户那份原型 86% 是脚本，
点选到的东西源码里根本不存在。没有这一步，模型只能自己猜关键词——
实测猜了八轮（badge(d.status、cx-badge、data-cx…）仍然两手空空。

样例取自那份真原型的 5690–5800 行，含两处标准答案：
  第 10 行  const badge=(t,c)=>'<span class="cx-badge '+...   ← 标签怎么拼
  第 79 行  cell(badge(a.status, a.status==='启用'?...))      ← 这一列怎么填
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import dynamic   # noqa: E402

PAGE = (Path(__file__).parent / "fixtures" / "dynamic_page.html").read_text("utf-8")
BADGE = '<span class="cx-badge green">启用</span>'
DEFINE_LINE, CALL_LINE = 10, 79


class Fingerprint(unittest.TestCase):
    def test_挑出能用来搜的特征(self):
        mark = dynamic.fingerprint(BADGE)
        self.assertEqual(mark["tag"], "span")
        self.assertIn("cx-badge", mark["distinct_classes"])
        self.assertNotIn("green", mark["distinct_classes"], "颜色词到处都是，拿它搜等于没搜")
        self.assertEqual(mark["text"], "启用")
        self.assertTrue(mark["text_is_literal"])

    def test_纯数字不当线索(self):
        """「8,929.61」是数据不是模板，拿它搜只会搜到数据源。"""
        mark = dynamic.fingerprint('<div class="kpi-value">8,929.61</div>')
        self.assertFalse(mark["text_is_literal"])

    def test_data属性优先(self):
        mark = dynamic.fingerprint('<button data-action="af-edit" data-id="A3">编辑</button>')
        self.assertIn("data-action", mark["data_keys"])
        self.assertIn("af-edit", mark["data_values"])

    def test_畸形片段不炸(self):
        for junk in ("", "<span class=", "纯文字", "<<>>"):
            with self.subTest(junk=junk):
                self.assertIsInstance(dynamic.fingerprint(junk), dict)


class FindOrigin(unittest.TestCase):
    def hits(self, outer=BADGE):
        return [h["line"] for h in dynamic.origin_hints(PAGE, outer)["hits"]]

    def test_找到标签是怎么拼的(self):
        self.assertIn(DEFINE_LINE, self.hits())

    def test_也找到这一列是怎么填的(self):
        """只找到「badge 长什么样」解决一半；用户要改的往往是调用处。"""
        self.assertIn(CALL_LINE, self.hits())

    def test_两处都排在前面(self):
        """排在第二十位等于没找到——模型不会翻到那儿。"""
        hits = self.hits()
        self.assertLess(hits.index(DEFINE_LINE), 8)
        self.assertLess(hits.index(CALL_LINE), 8)

    def test_不在脚本里的行不算(self):
        """CSS 里也有 .cx-badge，但改样式表解决不了"这个标签能不能点"。"""
        for line in dynamic.origin_hints(PAGE, BADGE)["hits"]:
            self.assertNotIn("padding:2px 6px", line["code"])

    def test_找不到时老老实实返回空(self):
        found = dynamic.origin_hints(PAGE, '<span class="zzz-never-here">不存在</span>')
        self.assertEqual(found["hits"], [])
        self.assertEqual(dynamic.hint_text(PAGE, '<span class="zzz-never-here">不存在</span>'), "")

    def test_提示语讲清了该怎么办(self):
        text = dynamic.hint_text(PAGE, BADGE)
        self.assertIn("运行时生成", text)
        self.assertIn("改 DOM 没用", text)
        self.assertIn(f"第 {CALL_LINE} 行", text)
        self.assertIn("不要再去全页搜", text)


class WiredIntoAgent(unittest.TestCase):
    def test_源码里本来就有的元素不加提示(self):
        """静态元素照常走定位，别平白多塞一段话进提示词。"""
        from backend import agent
        page = "<!doctype html><html><head><title>t</title></head><body><h1 id='t'>标题</h1></body></html>"
        note = agent.dynamic_origin_note(page, [{"selector": "#t", "outer_html": "<h1 id='t'>标题</h1>"}])
        self.assertEqual(note, "")

    def test_动态元素会带上线索(self):
        from backend import agent
        note = agent.dynamic_origin_note(
            PAGE, [{"selector": "tbody tr td span", "outer_html": BADGE}])
        self.assertIn("运行时生成", note)
        self.assertIn(f"第 {DEFINE_LINE} 行", note)

    def test_最多带两个元素的线索(self):
        """框选可能一次选中十几个，全塞进去会把提示词撑爆。"""
        from backend import agent
        many = [{"selector": f"tbody tr:nth-child({i}) span", "outer_html": BADGE} for i in range(6)]
        self.assertLessEqual(agent.dynamic_origin_note(PAGE, many).count("运行时生成"), 2)


if __name__ == "__main__":
    unittest.main()
