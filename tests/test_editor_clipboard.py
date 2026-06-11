from pathlib import Path
import unittest


class EditorClipboardTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.html = (root / 'index.html').read_text(encoding='utf-8')

    def test_clipboard_html_api_is_preferred_over_exec_command(self):
        clipboard_pos = self.html.index("navigator.clipboard.write")
        exec_pos = self.html.index("document.execCommand('copy')")
        self.assertLess(clipboard_pos, exec_pos)

    def test_clipboard_html_is_wrapped_with_white_background(self):
        self.assertIn('function buildClipboardHtml', self.html)
        self.assertIn('background:#fff', self.html)
        self.assertIn('color:#3f3f3f', self.html)


if __name__ == '__main__':
    unittest.main()
