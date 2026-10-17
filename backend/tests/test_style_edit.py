"""编辑模式的属性分组：能写的属性和值是封闭的一组，一次修改可以带几条样式。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.patcher import apply_operations, style_ops, PatchError, SHADOWS   # noqa: E402

PAGE = '<html><head><style>:root{--color-primary:#b8532f}</style></head><body><div id="card"><h2 id="t">标题</h2></div></body></html>'


def style(name, value, selector='#card'):
    out, _ = apply_operations(PAGE, [{'action': 'set_style', 'selector': selector, 'name': name, 'value': value}])
    return out


class 能写的值(unittest.TestCase):
    def test_尺寸布局文字效果都能写(self):
        for name, value in [('width', 'fit-content'), ('width', '100%'), ('height', '240px'), ('flex', '1 1 0%'),
                            ('display', 'flex'), ('flex-direction', 'column'), ('gap', '12px'), ('align-items', 'center'),
                            ('justify-content', 'space-between'), ('margin-top', '-8px'), ('margin-left', 'auto'),
                            ('font-weight', '600'), ('line-height', '22px'), ('letter-spacing', '-0.5px'), ('text-align', 'center'),
                            ('color', '#1a2b3c'), ('background-color', 'transparent'), ('border-width', '1px'),
                            ('border-style', 'dashed'), ('border-color', 'var(--color-primary)'), ('opacity', '0.5'),
                            ('box-shadow', '0 4px 12px rgba(0,0,0,.08)'), ('font-size', '13.5px')]:
            self.assertIn(f'#card {{ {name}: {value} !important; }}', style(name, value), name)

    def test_不在白名单的值和属性都拦下(self):
        for name, value in [('width', '50vw'), ('width', '1000px'), ('color', 'red;} body{display:none'), ('color', '#12'),
                            ('opacity', '2'), ('box-shadow', '0 0 0 9999px red'), ('display', 'contents'),
                            ('position', 'absolute'), ('font-weight', '450'), ('gap', '-4px'), ('padding-top', '-4px')]:
            with self.assertRaises(PatchError, msg=f'{name}: {value}'):
                style(name, value)

    def test_阴影档位和前端一致(self):
        front = (Path(__file__).resolve().parents[2] / 'frontend/src/components/layout/InspectorPanel.vue').read_text(encoding='utf-8')
        for value in SHADOWS:
            self.assertIn(f"'{value}'", front)


class 一次改几条(unittest.TestCase):
    def test_横向排列是一次修改(self):
        ops = style_ops(PAGE, 'set_style', '#card', 'display', 'flex', {'flex-direction': 'row'})
        out, _ = apply_operations(PAGE, ops)
        self.assertIn('display: flex', out)
        self.assertIn('flex-direction: row', out)

    def test_用到没有的设计变量会补上(self):
        ops = style_ops(PAGE, 'set_style', '#card', 'color', 'var(--color-text)', {'border-color': 'var(--color-text)'})
        self.assertEqual([o['action'] for o in ops].count('set_token'), 1)

    def test_不能夹带文字和变量(self):
        with self.assertRaises(PatchError):
            style_ops(PAGE, 'set_style', '#card', 'width', '10px', {'text': 'x'})
        with self.assertRaises(PatchError):
            style_ops(PAGE, 'set_style', '#card', 'width', '10px', {'--a': '#fff'})


if __name__ == '__main__':
    unittest.main()
