"""skill 的触发说明。

模型平时只看得到一行字，全靠它判断这轮该不该展开这个 skill。
那一行必须是「什么时候用它」，不能是名字——拿名字判断不了。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import skills   # noqa: E402


def entry(text):
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "包"
        folder.mkdir()
        (folder / "SKILL.md").write_text(text, "utf-8")
        return skills._entry(folder)


class Description(unittest.TestCase):
    def test_优先用_frontmatter_的_description(self):
        got = entry("---\nname: 甲\ndescription: 做报表页时用\n---\n# 标题\n## 用途\n别的说法\n")
        self.assertEqual(got["description"], "做报表页时用")

    def test_没有_frontmatter_时读正文的用途一节(self):
        """手写 SKILL.md 的人通常写「## 用途」，而不是去记 YAML 写法。"""
        got = entry("# 零碳园区 UI Skill\n\n## 用途\n当用户要求生成、修改零碳园区平台页面时，使用本 Skill。\n\n## 必读顺序\n1. a.md\n")
        self.assertIn("当用户要求生成", got["description"])
        self.assertNotIn("必读顺序", got["description"], "只取用途那一节，不要把后面的内容也卷进来")

    def test_各种写法的用途标题都认(self):
        for heading in ("## 用途", "# 何时使用", "### 适用场景", "## When to use", "## Usage"):
            with self.subTest(heading=heading):
                got = entry(f"# 名字\n\n{heading}\n做表格页时用它。\n")
                self.assertIn("做表格页时用它", got["description"])

    def test_只有名字时明说模型只能靠猜(self):
        got = entry("# 某个 Skill\n\n## 规则\n随便写点什么\n")
        self.assertIn("只能按这个名字猜", got["description"],
                      "退回去取标题时要讲明白，否则用户不知道自己的 skill 触发不了")

    def test_描述长度有上限(self):
        got = entry("# 名字\n\n## 用途\n" + "很长的说明。" * 80)
        self.assertLessEqual(len(got["description"]), 160)

    def test_没有_SKILL_md_就不是一个_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "空包"
            folder.mkdir()
            (folder / "README.md").write_text("只有说明", "utf-8")
            self.assertIsNone(skills._entry(folder))


if __name__ == "__main__":
    unittest.main()


class IndexBlock(unittest.TestCase):
    """用户把 skill 装进来就是要它生效，不该再让模型猜该不该用。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._root = skills.ROOT
        self.addCleanup(lambda: setattr(skills, "ROOT", self._root))
        skills.ROOT = Path(self.tmp.name)

    def add(self, name, body):
        folder = skills.ROOT / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(body, "utf-8")
        return folder

    def test_短正文直接常驻在提示词里(self):
        self.add("ui", "# UI Skill\n\n## 用途\n做后台页面时用\n\n## 硬约束\n- 主色 #1D5BFF\n- 基准字号 12px\n")
        block = skills.index_block()
        self.assertIn("#1D5BFF", block, "硬约束必须每轮都在模型眼前，而不是藏在一次猜测后面")
        self.assertIn("默认就按它做", block)

    def test_附带文件不塞进提示词(self):
        folder = self.add("ui", "# UI\n\n## 用途\n做页面\n")
        (folder / "assets").mkdir()
        (folder / "assets" / "big.html").write_text("X" * 40000, "utf-8")
        block = skills.index_block()
        self.assertIn("assets/big.html", block, "要告诉模型有这个文件")
        self.assertNotIn("X" * 200, block, "但 40KB 的组件库不能塞进每一轮")

    def test_正文过长时退回只给说明(self):
        self.add("huge", "# 大包\n\n## 用途\n特别大的包\n\n" + "填充内容。" * 4000)
        block = skills.index_block()
        self.assertIn("特别大的包", block)
        self.assertNotIn("特别大的包 填充内容", block,
                         "用途一节到空行为止，后面的正文不能被卷进描述里")
        self.assertNotIn("填充内容。" * 50, block)
        self.assertIn("对得上就用 read_skill", block)

    def test_总量有预算多个包不会撑爆提示词(self):
        for i in range(12):
            self.add(f"pack{i}", f"# 包{i}\n\n## 用途\n用途{i}\n\n" + "内容。" * 500)
        self.assertLessEqual(len(skills.index_block()), skills.INLINE_BUDGET + 3000)

    def test_没有_skill_时不占位置(self):
        self.assertEqual(skills.index_block(), "")

    def test_skill_管不着用户这轮要什么(self):
        self.add("ui", "# UI\n\n## 用途\n做页面\n")
        self.assertIn("听用户的", skills.index_block(),
                      "规范管怎么做，不能盖过用户这一轮的要求")
