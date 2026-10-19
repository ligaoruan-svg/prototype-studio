"""软件自带的几套风格，以及每个项目选一套：内置只读、我的、不选；以前的项目行为不变。"""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import agent, patcher, skill_digest, skills, storage   # noqa: E402
try:
    from backend import server   # 要装了 fastapi 才能测接口
except ImportError:
    server = None

BUILTIN = ["简洁后台", "企业蓝", "极简黑白", "业务中台", "数据中台", "数据大屏", "移动端App", "温暖柔和", "活力电商"]


def skill_zip(name: str, shell: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{name}/SKILL.md", f"---\nname: {name}\ndescription: 测试用\n---\n# {name}\n规矩正文")
        if shell:
            z.writestr(f"{name}/assets/页面外壳.html", "<html><style>:root{--primary:#123456;--bg:#fafafa;}</style>"
                       "<script>const NAV=[/*PA:NAV*/\n];const Pages={/*PA:PAGES*/\n};function bindPage(page){/*PA:BIND*/\n}</script></html>")
    return buf.getvalue()


class 内置风格(unittest.TestCase):
    def test_三套都在_带外壳_能过检查(self):
        items = skills.builtin_listing()
        self.assertEqual([i["name"] for i in items], BUILTIN)
        self.assertEqual([i["category"] for i in items], ["后台"] * 3 + ["中台"] * 3 + ["手机"] * 3)
        self.assertEqual({i["layout"] for i in items}, {"sidebar", "topbar", "screen", "mobile"})
        for item in items:
            self.assertTrue(item["builtin"] and item["has_shell"] and item["has_preview"] and item["tagline"])
            self.assertNotIn("preview.png", item["files"])   # 预览图不算 skill 的附带文件，不进 AI 的清单
            self.assertTrue(skills.preview_path("builtin", item["folder"]))
            shell = skill_digest.find_shell({"style": "builtin:" + item["folder"]})[2]
            self.assertTrue(agent.verify_source(shell)["ok"], item["name"])
            self.assertTrue(agent.is_fresh_shell(shell))
            self.assertNotIn("零碳", shell)
            filled = patcher.shell_add(shell, nav="{key:'a',label:'甲',items:[{key:'x',label:'页'}]}",
                                       pages="x(){return pageShell('页','',Card({title:'t',body:'b'}))}")
            self.assertFalse(agent.is_fresh_shell(filled))   # 写了内容就不再是空外壳
            self.assertNotIn("{key:'home',label:'首页'}", filled)

    def test_菜单只写了页面或多包一层也能用(self):
        shell = skill_digest.find_shell({"style": "builtin:移动端App"})[2]
        for nav in ("[{key:'a',label:'甲',icon:'home'},{key:'b',label:'乙'}]",   # 这次真出过的：多包一层 []、没有分组
                    "{key:'a',label:'甲'},{key:'b',label:'乙'}"):
            out = patcher.shell_add(shell, nav=nav, pages="a(){return pageShell('甲','',Card({title:'t',body:'b'}))}")
            line = out.split("const NAV=[/*PA:NAV*/\n", 1)[1].split("\n", 1)[0]
            self.assertTrue(line.strip().startswith("{key:'main',label:'功能',items:[{key:'a'"), line)
        normal = "{key:'g',label:'组',items:[{key:'a',label:'甲'}]}"
        out = patcher.shell_add(shell, nav=normal)
        self.assertIn("/*PA:NAV*/\n  " + normal + ",", out)
        for item in skills.builtin_listing():   # 外壳自己也兜着：散的页面不会让 g.items.map 崩掉
            text = skill_digest.find_shell({"style": "builtin:" + item["folder"]})[2]
            self.assertIn("const navGroups=()=>NAV.flat()", text)
            self.assertNotIn("NAV[0].items", text)

    def test_生成脚本和仓库里的一致(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        import importlib
        gen = importlib.import_module("生成内置风格")
        for style in gen.STYLES:
            skill, shell = gen.build(style)
            folder = skills.BUILTIN / style["name"]
            self.assertEqual((folder / "SKILL.md").read_text("utf-8"), skill, "改了生成脚本要重新跑一遍")
            self.assertEqual((folder / "assets" / "页面外壳.html").read_text("utf-8"), shell)

    def test_内置的删不掉(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, skills.ROOT = skills.ROOT, Path(tmp)
            try:
                self.assertFalse(skills.remove("简洁后台"))
            finally:
                skills.ROOT = old
        self.assertTrue((skills.BUILTIN / "简洁后台" / "SKILL.md").is_file())


@unittest.skipIf(server is None, "没装 fastapi")
class 每个项目一套风格(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data, self.old_root = storage.DATA_ROOT, skills.ROOT
        storage.DATA_ROOT = Path(self.tmp.name) / "projects"
        storage.DATA_ROOT.mkdir()
        skills.ROOT = Path(self.tmp.name) / "skills"
        skills.ROOT.mkdir()
        skills.import_archive(skill_zip("我的风格"))
        skills.import_archive(skill_zip("只有说明", shell=False))

    def tearDown(self):
        storage.DATA_ROOT, skills.ROOT = self.old_data, self.old_root
        self.tmp.cleanup()

    def test_检查风格值(self):
        self.assertEqual(skills.check_style("none"), "none")
        self.assertEqual(skills.check_style("builtin:数据大屏"), "builtin:数据大屏")
        self.assertEqual(skills.check_style("mine:我的风格"), "mine:我的风格")
        for bad in ("", "builtin:没有这个", "mine:简洁后台", "x:y", "builtin:../etc"):
            with self.assertRaises(ValueError):
                skills.check_style(bad)

    def test_生效的只有选的那一套(self):
        self.assertEqual({i["folder"] for i in skills.active({})}, {"我的风格", "只有说明"})   # 以前的项目：照旧全部
        self.assertEqual(skills.active({"style": "none"}), [])
        self.assertEqual([i["folder"] for i in skills.active({"style": "builtin:简洁后台"})], ["简洁后台"])
        self.assertEqual([i["folder"] for i in skills.active({"style": "mine:我的风格"})], ["我的风格"])
        self.assertEqual(skills.active({"style": "mine:被删了"}), [])
        block = skills.index_block({"style": "builtin:数据大屏"})
        self.assertIn("这个项目选的风格", block)
        self.assertIn("数据大屏", block)
        self.assertNotIn("我的风格", block)
        self.assertEqual(skills.index_block({"style": "none"}), "")
        self.assertIsNone(skill_digest.find_shell({"style": "none"}))
        self.assertIsNone(skill_digest.find_shell({"style": "mine:只有说明"}))

    def test_我的风格的缩略图取外壳里的颜色(self):
        item = next(i for i in skills.listing() if i["folder"] == "我的风格")
        self.assertEqual((item["primary"], item["background"], item["has_shell"], item["builtin"]),
                         ("#123456", "#fafafa", True, False))

    def test_按风格新建_第一页就是外壳(self):
        meta = server.new_project(server.NewProjectIn(name="订单'后台</script>", style="builtin:简洁后台"))
        self.assertEqual(meta["style"], "builtin:简洁后台")
        html = storage.read_page(meta["id"], meta["pages"][0]["id"])
        self.assertTrue(agent.is_fresh_shell(html))
        self.assertIn('const APP_NAME="订单\'后台\\u003c/script>";', html)
        self.assertIn("<title>订单&#x27;后台&lt;/script&gt;</title>", html)
        self.assertEqual(server.get_project(meta["id"])["style"], "builtin:简洁后台")

    def test_不选风格_用空白骨架(self):
        meta = server.new_project(server.NewProjectIn(name="随便", style="none"))
        html = storage.read_page(meta["id"], meta["pages"][0]["id"])
        self.assertFalse(agent.is_fresh_shell(html))
        self.assertEqual(server.get_project(meta["id"])["style"], "none")

    def test_风格不对就不建(self):
        with self.assertRaises(server.HTTPException):
            server.new_project(server.NewProjectIn(name="x", style="builtin:没有"))
        self.assertEqual(storage.list_projects(), [])

    def test_导入的原型默认不选(self):
        meta = server._import_upload("旧.html", b"<html><body>hi</body></html>", "")
        self.assertEqual(server.get_project(meta["id"])["style"], "none")

    def test_以前的项目显示为旧方式_换风格后生效(self):
        pid = storage.create_project("旧")["id"]
        self.assertEqual(server.get_project(pid)["style"], "legacy")
        self.assertEqual(server.set_project_style(pid, server.StyleIn(style="mine:我的风格"))["style"], "mine:我的风格")
        self.assertEqual(storage.load_meta(pid)["style"], "mine:我的风格")
        with self.assertRaises(server.HTTPException):
            server.set_project_style(pid, server.StyleIn(style="mine:没有"))

    def test_换风格时空页面跟着换_写过内容的不动(self):
        meta = server.new_project(server.NewProjectIn(name="看板", style="builtin:数据大屏"))
        pid, page = meta["id"], meta["pages"][0]["id"]
        out = server.set_project_style(pid, server.StyleIn(style="builtin:移动端App"))
        self.assertEqual(out["swapped"], 1)
        html = storage.read_page(pid, page)
        self.assertIn("class=\"tabbar\"", html.split("<script>")[1] + html)   # 手机外壳
        self.assertIn("移动端App", html)
        self.assertEqual(server.set_project_style(pid, server.StyleIn(style="none"))["swapped"], 1)
        self.assertFalse(agent.is_fresh_shell(storage.read_page(pid, page)))   # 空白骨架
        self.assertEqual(server.set_project_style(pid, server.StyleIn(style="builtin:简洁后台"))["swapped"], 1)
        filled = patcher.shell_add(storage.read_page(pid, page), nav="{key:'a',label:'甲',items:[{key:'x',label:'页'}]}",
                                   pages="x(){return pageShell('页','','<p>内容</p>')}")
        storage.write_page(pid, page, filled, "AI 写了内容")
        self.assertEqual(server.set_project_style(pid, server.StyleIn(style="builtin:数据大屏"))["swapped"], 0)
        self.assertEqual(storage.read_page(pid, page), filled)

    def test_风格清单(self):
        out = server.list_styles()
        self.assertEqual([i["name"] for i in out["builtin"]], BUILTIN)
        self.assertEqual({i["folder"] for i in out["mine"]}, {"我的风格", "只有说明"})


if __name__ == "__main__":
    unittest.main()
