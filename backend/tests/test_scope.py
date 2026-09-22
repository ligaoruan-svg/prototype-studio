"""改动范围检查：该报的报、不该报的不报。

误报比漏报更伤——每次都提示"超界了"，用户很快就不看了。
所以公共区（style / script / head）和紧邻插入一律放行。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.experience import scope_report   # noqa: E402

PAGE = """<!doctype html>
<html>
<head>
<style>
.btn { color: red; }
</style>
</head>
<body>
<header class="site-nav">
  <h1>标题</h1>
  <nav>导航</nav>
</header>
<main>
  <button id="save" class="btn">保存</button>
  <p>说明文字</p>
</main>
<footer>页脚</footer>
</body>
</html>"""

SELECTED = [{"id": "a1", "selector": "#save", "tag": "button", "text": "保存"}]


def edit(*pairs):
    out = PAGE
    for old, new in pairs:
        assert old in out, old
        out = out.replace(old, new)
    return out


class InScope(unittest.TestCase):
    """这些都是正当改动，一条都不该提示。"""

    def check(self, after):
        self.assertIsNone(scope_report(PAGE, after, SELECTED))

    def test_只改选中的元素(self):
        self.check(edit((">保存<", ">提交<")))

    def test_顺带加一条样式规则(self):
        self.check(edit((">保存<", ">提交<"), ("color: red;", "color: red; font-size: 12px;")))

    def test_新增一整段脚本(self):
        self.check(edit(("</body>", "<script>console.log(1)</script>\n</body>")))

    def test_在选中元素紧后面插入兄弟节点(self):
        self.check(edit(('<button id="save" class="btn">保存</button>',
                         '<button id="save" class="btn">保存</button>\n  <button class="btn">取消</button>')))

    def test_整行重写选中元素(self):
        self.check(edit(('  <button id="save" class="btn">保存</button>',
                         '  <button id="save" class="btn primary" type="submit">立即保存</button>')))

    def test_没有改动(self):
        self.check(PAGE)

    def test_用户没圈任何元素时不做判断(self):
        self.assertIsNone(scope_report(PAGE, edit(("页脚", "新页脚")), []))

    def test_选择器在旧源码里找不到时不做判断(self):
        self.assertIsNone(scope_report(PAGE, edit(("页脚", "新页脚")),
                                       [{"id": "x", "selector": "#nope"}]))


class OutOfScope(unittest.TestCase):
    """这些是改到了圈定范围之外，必须提示。"""

    def check(self, after, place):
        result = scope_report(PAGE, after, SELECTED)
        self.assertIsNotNone(result, "应当提示超界")
        self.assertGreater(result["lines"], 0)
        self.assertIn(place, result["places"])

    def test_顺手重写了页头(self):
        self.check(edit(("<h1>标题</h1>", "<h1>全新标题</h1>"),
                        ("<nav>导航</nav>", "<nav>首页 / 关于</nav>")), "header.site-nav")

    def test_同时动了页脚(self):
        self.check(edit((">保存<", ">提交<"),
                        ("<footer>页脚</footer>", "<footer>版权 2026</footer>")), "footer")

    def test_删掉了旁边的段落(self):
        self.check(edit(("  <p>说明文字</p>\n", "")), "main")

    def test_改掉了旁边的段落(self):
        self.check(edit(("<p>说明文字</p>", "<p>换掉的文字</p>")), "main")

    def test_新增脚本是正当的但同时动页脚不是(self):
        self.check(edit(("</body>", "<script>console.log(1)</script>\n</body>"),
                        ("<footer>页脚</footer>", "<footer>版权 2026</footer>")), "footer")


if __name__ == "__main__":
    unittest.main()
