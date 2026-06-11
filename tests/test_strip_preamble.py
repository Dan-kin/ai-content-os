import unittest

import llm_config


class StripPreambleTest(unittest.TestCase):
    def test_strips_greeting_and_separator(self):
        text = '主人，以下是改写后的小红书笔记：\n\n---\n\n🚴 正文开始'
        self.assertEqual(llm_config.strip_preamble(text), '🚴 正文开始')

    def test_strips_plain_preamble_line(self):
        text = '好的，这是转换结果：\n# 标题\n\n正文'
        self.assertEqual(llm_config.strip_preamble(text), '# 标题\n\n正文')

    def test_keeps_clean_output_untouched(self):
        text = '# 标题\n\n正文内容。'
        self.assertEqual(llm_config.strip_preamble(text), text)

    def test_keeps_content_starting_with_keyword_but_long(self):
        # 正文恰好以"这是"开头且不是寒暄（无冒号结尾、长句）时不应误删
        text = '这是一篇关于 AI 的深度文章，我们将从三个角度展开讨论这个话题的来龙去脉与未来走向'
        self.assertEqual(llm_config.strip_preamble(text), text)

    def test_empty_input(self):
        self.assertEqual(llm_config.strip_preamble(''), '')
        self.assertEqual(llm_config.strip_preamble(None), '')


if __name__ == '__main__':
    unittest.main()
