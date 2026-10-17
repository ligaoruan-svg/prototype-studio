"""讨论给出的建议：短标题 + 一句人话 + 给 AI 的指令，只推荐一条并排在第一。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.conversation import discussion_result   # noqa: E402


def s(label, rec=None, summary='一句话'):
    item = {'label': label, 'summary': summary, 'instruction': label + ' 的完整做法'}
    if rec is not None:
        item['recommended'] = rec
    return item


class 建议(unittest.TestCase):
    def test_推荐的排第一且只有一条(self):
        out = discussion_result('结论', [s('甲'), s('乙', True), s('丙', True)])['suggestions']
        self.assertEqual([x['label'] for x in out], ['乙', '甲', '丙'])
        self.assertEqual([x['recommended'] for x in out], [True, False, False])

    def test_没标推荐就推荐第一条(self):
        out = discussion_result('结论', [s('甲'), s('乙')])['suggestions']
        self.assertEqual([x['recommended'] for x in out], [True, False])

    def test_一句话说明会带上_缺了也不报错(self):
        out = discussion_result('结论', [s('甲', summary='设备管理下加一页'), {'label': '乙', 'instruction': 'x'}])['suggestions']
        self.assertEqual(out[0]['summary'], '设备管理下加一页')
        self.assertEqual(out[1]['summary'], '')

    def test_推荐只认布尔真(self):
        out = discussion_result('结论', [s('甲'), s('乙', 'true')])['suggestions']
        self.assertEqual(out[0]['label'], '甲')


if __name__ == '__main__':
    unittest.main()
