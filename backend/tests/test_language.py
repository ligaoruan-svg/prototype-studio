"""界面语言：界面不是中文时，告诉 AI 用用户的语言回复；程序代发的中文指令不能带偏"""
import unittest
from pathlib import Path

from backend.agent import language_note

ROOT = Path(__file__).resolve().parents[2]


class LanguageTest(unittest.TestCase):
    def test_note_names_language(self):
        note = language_note('en')
        self.assertIn('English', note)
        self.assertIn('程序代发的中文指令', note)

    def test_unknown_language_falls_back_to_code(self):
        self.assertIn('ja', language_note('ja'))

    def test_prompts_have_language_rule(self):
        for name in ('agent-system.md', 'discussion-system.md'):
            text = (ROOT / 'prompts' / name).read_text(encoding='utf-8')
            self.assertIn('# 语言', text)
            self.assertIn('用用户说话的语言回复', text)


if __name__ == '__main__':
    unittest.main()
