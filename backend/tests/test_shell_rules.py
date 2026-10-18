"""从页面外壳起步的页面：交互只管当前页、脚本全加载完才渲染。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.patcher import verify_source, new_issues, apply_operations, PatchError   # noqa: E402

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


class 往外壳里加页面(unittest.TestCase):
    OP = {'action': 'shell_add', 'nav': "{key:'carbon',label:'碳管理',items:[{key:'quota',label:'碳配额'}]}",
          'pages': "quota(){return pageShell('碳配额','',quotaBody())}",
          'bind': "if(page==='quota'){document.getElementById('content').dataset.ok='1'}",
          'script': "const quotaState={page:1};function quotaBody(){return '<p>配额</p>'}"}

    def test_一次写完四处_占位首页删掉(self):
        out, _ = apply_operations(SHELL, [self.OP])
        self.assertIn("{key:'carbon'", out)
        self.assertNotIn("label:'首页'", out)
        self.assertNotIn('在这里写这一页的内容', out)
        self.assertLess(out.index('function quotaBody'), out.index('const Pages='))
        self.assertTrue(verify_source(out)['ok'], verify_source(out)['issues'])

    def test_再加一页_前面的留着(self):
        once, _ = apply_operations(SHELL, [self.OP])
        two = {'action': 'shell_add', 'nav': "{key:'energy',label:'能耗',items:[{key:'mon',label:'监测'}]},",
               'pages': "mon(){return pageShell('监测','','<p>监测</p>')},"}
        out, _ = apply_operations(once, [two])
        self.assertIn("{key:'carbon'", out); self.assertIn("{key:'energy'", out)
        self.assertIn("mon(){", out); self.assertIn("quota(){", out)
        self.assertTrue(verify_source(out)['ok'], verify_source(out)['issues'])

    def test_不是外壳的页面不能用(self):
        with self.assertRaises(PatchError):
            apply_operations('<html><head></head><body></body></html>', [self.OP])


class 外壳页面的其他规矩(unittest.TestCase):
    def test_不许整页跳转(self):
        bad = SHELL.replace('</body>', "<script>function reset(){location.reload()}</script></body>")
        self.assertTrue(any('页面跳转' in i for i in new_issues(verify_source(SHELL), verify_source(bad))))

    def test_外壳接口摘要(self):
        from backend.agent import shell_api
        api = shell_api(SHELL)
        self.assertIn('ZeroUI.Toast(message,type)', api['ZeroUI'])
        self.assertIn('ZeroUI.Button({label,kind,icon,id,disabled,loading})', api['ZeroUI'])
        self.assertIn('data-table', api['css'])


if __name__ == '__main__':
    unittest.main()
