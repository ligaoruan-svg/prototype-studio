"""从页面外壳起步的页面：交互只管当前页、脚本全加载完才渲染。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.patcher import verify_source, new_issues   # noqa: E402

SHELL = (ROOT / 'prompts/skills/零碳园区_UI_Skill包_v3/assets/页面外壳.html').read_text(encoding='utf-8')


class 外壳规则(unittest.TestCase):
    def test_外壳本身通过检查(self):
        self.assertTrue(verify_source(SHELL)['ok'], verify_source(SHELL)['issues'])

    def test_等脚本都加载完再渲染(self):
        self.assertIn("document.addEventListener('DOMContentLoaded',boot)", SHELL)
        self.assertNotIn('\nRouter.render();\n</script>', SHELL)

    def test_有只管当前页的事件写法(self):
        self.assertIn('const PageEvents=', SHELL)
        self.assertIn('h.page!==page', SHELL)

    def test_新加的全局点击监听会被拦(self):
        bad = SHELL.replace('</body>', "<script>document.addEventListener('click',e=>{if(e.target.dataset.pageGo)page=1})</script></body>")
        self.assertEqual(len(new_issues(verify_source(SHELL), verify_source(bad))), 1)

    def test_原来就有的不拦(self):
        bad = SHELL.replace('</body>', "<script>document.addEventListener('click',()=>{})</script></body>")
        worse = bad.replace('</body>', "<script>document.addEventListener('click',()=>{})</script></body>")
        self.assertEqual(new_issues(verify_source(bad), verify_source(worse)), [])

    def test_不是外壳的页面不管(self):
        page = '<html><head></head><body><script>document.addEventListener("click",()=>{})</script></body></html>'
        self.assertTrue(verify_source(page)['ok'])

    def test_分页列出全部页码(self):
        self.assertIn('Array.from({length:pages}', SHELL)


if __name__ == '__main__':
    unittest.main()
