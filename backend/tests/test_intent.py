"""意图路由回归。

判错的代价不对称：把提问当成修改，会无端改动用户的文件；
把指令当成提问，只是白问一轮。所以拿不准一律走讨论——
但「按你的建议改一下」这种明确指令不能因为句子里有个「建议」就被判成提问。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.conversation import resolve_intent   # noqa: E402

EDIT = [
    # 用户点「按此建议修改」时应用自己拼的前缀，里面就带着「建议」二字
    '按已讨论的建议修改：给所有表格数字列的千位以上数值加千分位（如 1500 → 1,500）',
    '按你刚才的建议改一下',
    '加千分位',                      # 动词开头的祈使句，词表里没有这个词
    '能不能帮我改一下这个按钮',        # 客气的问法，实际是指令
    '请帮忙把表头固定住',              # 「请」+「帮忙」+「把」连用
    '把按钮改成蓝色', '改一下', '帮我改改这个标题', '删除这一行',
    '统一一下间距', '对齐这几个输入框', '换个配色', '去掉这个边框', '加粗标题',
    '插入一个筛选器', '把这几列排成两行', '再小一点点',
    'change the button color', 'fix the alignment',
]

DISCUSS = [
    '加个按钮是不是更好',              # 有动词，但整句在征求意见
    '要不要加个搜索', '有什么建议吗', '这个设计怎么样', '你觉得这里规范吗？美观吗？',
    '先别改，帮我看看哪里有问题', '为什么这里对不齐', '这里怎么改比较好',
    '哪些地方可以优化', '解释一下这段脚本', '值得做成弹窗吗', '行不行',
    '这样合理吗', '有没有更好的做法',
    'review this page', 'why is this misaligned', 'what should I change here',
]


# 两头都容易误伤的说法：话题词（讨论 / 建议 / 分析）和祈使句混在一起时的判定
MIXED_EDIT = [
    '按分析结果优化一下这个表格', '优化一下这个分析页', '我觉得太挤了，帮我改一下',
    '稍微宽一点', '再紧一点点', '按刚才讨论的改', '给这列右对齐', '这几处都调整',
]
MIXED_DISCUSS = [
    '我们讨论一下这个布局', '聊聊这个位置', '分析一下这个页面', '你觉得怎么样',
    '给点建议', '能不能说说为什么', '哪个方案更好', '要不要把这列右对齐',
    '这样改行不行', '为什么要删掉空白行', '这里怎么改', '哪里该改', '要不要改',
]


class Routing(unittest.TestCase):
    def test_指令走修改(self):
        for text in EDIT:
            with self.subTest(text=text):
                self.assertEqual(resolve_intent(text), 'edit')

    def test_提问走讨论(self):
        for text in DISCUSS:
            with self.subTest(text=text):
                self.assertEqual(resolve_intent(text), 'discuss')

    def test_话题词混在祈使句里时听指令(self):
        for text in MIXED_EDIT:
            with self.subTest(text=text):
                self.assertEqual(resolve_intent(text), 'edit')

    def test_话题词单独出现时算提问(self):
        for text in MIXED_DISCUSS:
            with self.subTest(text=text):
                self.assertEqual(resolve_intent(text), 'discuss')

    def test_显式指定的意图不被覆盖(self):
        self.assertEqual(resolve_intent('这个设计怎么样', 'edit'), 'edit')
        self.assertEqual(resolve_intent('把按钮改成蓝色', 'discuss'), 'discuss')

    def test_空输入不炸(self):
        self.assertEqual(resolve_intent(''), 'discuss')
        self.assertEqual(resolve_intent('   '), 'discuss')


class NeedsTarget(unittest.TestCase):
    """「这个」「这里」没点选时，当场请用户指，别去几十万字符里猜。

    实测过一次：用户说「这个我想要点击有介绍内容」，模型搜了八轮
    才说出「你这个没有指代」。答案是对的，只是晚了八轮、烧了八轮。
    """

    def test_空指的说法要求指位置(self):
        from backend.conversation import needs_target
        for text in ('这个我想要点击有介绍内容', '这个太小了', '这里加个筛选',
                     '这块换个配色', '那个删掉', '它改成蓝色', '这个', '这个，改大一点'):
            with self.subTest(text=text):
                self.assertTrue(needs_target(text))

    def test_说清了是什么就不拦(self):
        from backend.conversation import needs_target
        for text in ('这个按钮改成蓝色', '这个表格加一列', '这个页面的标题改一下',
                     '把左侧菜单宽度改成 172px', '顶栏右侧加个导出按钮', '所有表格数字加千分位'):
            with self.subTest(text=text):
                self.assertFalse(needs_target(text))

    def test_没点选时零轮次回话(self):
        """这条守的是钱：以前这种话要烧八轮模型调用才换来一句"你没指"。"""
        import tempfile
        from pathlib import Path as P
        from backend import agent, storage
        root = storage.DATA_ROOT
        called = []

        def boom(*a, **k):
            called.append(1)
            raise AssertionError("不该调用模型")

        original = agent.chat
        agent.chat = boom
        self.addCleanup(lambda: setattr(agent, "chat", original))
        self.addCleanup(lambda: setattr(storage, "DATA_ROOT", root))
        with tempfile.TemporaryDirectory() as tmp:
            storage.DATA_ROOT = P(tmp)
            pid = storage.create_project("t")["id"]
            (storage.project_dir(pid) / "source").mkdir(parents=True, exist_ok=True)
            (storage.project_dir(pid) / "source" / "index.html").write_text(
                "<!doctype html><html><head><title>t</title></head><body><h1>x</h1></body></html>", "utf-8")
            page_id = storage.add_page(pid, "index.html", "首页")["id"]
            result = agent.run_agent(pid, page_id, "这个我想要点击有介绍内容", "k", "m", stream=False)
        self.assertTrue(result["need_target"])
        self.assertEqual(called, [], "一个 token 都不该花")
        self.assertEqual(result["usage"]["total_tokens"], 0)
        self.assertIn("点选", result["message"])
