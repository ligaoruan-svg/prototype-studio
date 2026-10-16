"""脚本生成的元素也能在编辑模式里直接改：样式按同类写规则，文字换源码里唯一那一处。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.patcher import apply_operations, literal_count, replace_literal, verify_source, PatchError   # noqa: E402

PAGE = ('<html><head><style>.metric{padding:8px}</style></head><body><div id="c"></div><script>'
        'const M=[{label:"设备总数",v:8},{label:"在线设备",v:4},{label:"待巡检",v:4}];'
        'c.innerHTML=M.map(m=>`<div class="metric"><div>${m.label}</div><div>${m.v}</div></div>`).join("")</script></body></html>')


class 脚本生成的元素(unittest.TestCase):
    def test_写死的标签能直接改(self):
        self.assertEqual(literal_count(PAGE, '设备总数'), 1)
        out = replace_literal(PAGE, '设备总数', '设备数量')
        self.assertIn('label:"设备数量"', out)
        self.assertTrue(verify_source(out)['ok'])

    def test_算出来的数和重复的字不能直接改(self):
        self.assertEqual(literal_count(PAGE, '4'), 0, '数字是算出来的')
        self.assertEqual(literal_count(PAGE, '50%'), 0)
        with self.assertRaises(PatchError):
            replace_literal(PAGE, '4', '5')
        doubled = PAGE.replace('待巡检', '设备总数')
        self.assertEqual(literal_count(doubled, '设备总数'), 2)
        with self.assertRaises(PatchError):
            replace_literal(doubled, '设备总数', 'x')

    def test_新文字不能打断脚本(self):
        for bad in ['a"b', "a'b", 'a`b', '${x}', 'a\\b', '<b>', 'a\nb']:
            with self.assertRaises(PatchError, msg=bad):
                replace_literal(PAGE, '设备总数', bad)

    def test_同类元素写一条样式规则(self):
        out, _ = apply_operations(PAGE, [{'action': 'set_rule', 'selector': 'div.metric > div:nth-of-type(2)', 'name': 'font-size', 'value': '28px'}])
        self.assertIn('div.metric > div:nth-of-type(2) { font-size: 28px !important; }', out)
        again, _ = apply_operations(out, [{'action': 'set_rule', 'selector': 'div.metric > div:nth-of-type(2)', 'name': 'font-size', 'value': '32px'}])
        self.assertEqual(again.count('div.metric > div:nth-of-type(2) {'), 1, '同一个属性再改是覆盖，不是叠加')
        with self.assertRaises(PatchError):
            apply_operations(PAGE, [{'action': 'set_rule', 'selector': 'div{}body', 'name': 'color', 'value': '12px'}])


if __name__ == '__main__':
    unittest.main()
