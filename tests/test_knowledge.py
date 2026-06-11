import os
import shutil
import tempfile
import unittest
from unittest import mock

import knowledge


class KnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('data', exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_and_get(self):
        kid = knowledge.add('Fable 5 定价', 'Fable 5 输入 $5/M tokens',
                            source_url='https://anthropic.com',
                            tags='模型,定价')
        item = knowledge.get(kid)
        self.assertEqual(item['title'], 'Fable 5 定价')
        self.assertEqual(item['tags'], '模型,定价')
        self.assertTrue(item['created_at'])

    def test_search_multi_keyword_and(self):
        knowledge.add('Fable 5 定价', '输入价格说明', tags='定价')
        knowledge.add('GLM 5 发布', '智谱新模型', tags='模型')
        knowledge.add('Fable 5 评测', '写作能力很强', tags='评测')
        hits = knowledge.search('Fable 定价')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['title'], 'Fable 5 定价')
        # 空关键词返回全部（按时间倒序）
        self.assertEqual(len(knowledge.search('')), 3)

    def test_delete(self):
        kid = knowledge.add('T', 'C')
        knowledge.delete(kid)
        self.assertIsNone(knowledge.get(kid))

    def test_add_requires_title_and_content(self):
        with self.assertRaises(ValueError):
            knowledge.add('', 'c')
        with self.assertRaises(ValueError):
            knowledge.add('t', '')

    def test_relevant_for_matches_title_words(self):
        knowledge.add('Fable 5 定价', '输入 $5/M')
        knowledge.add('小红书运营技巧', '多用 emoji')
        hits = knowledge.relevant_for('Fable 5 发布解读：价格与能力')
        titles = [h['title'] for h in hits]
        self.assertIn('Fable 5 定价', titles)
        self.assertNotIn('小红书运营技巧', titles)

    def test_relevant_for_limit_and_no_match(self):
        for i in range(10):
            knowledge.add('Agent 实践 %d' % i, '内容 %d' % i)
        hits = knowledge.relevant_for('Agent 工作流', limit=6)
        self.assertLessEqual(len(hits), 6)
        self.assertEqual(knowledge.relevant_for('完全无关主题词'), [])

    def test_import_url_extracts_text(self):
        html = ('<html><head><title>页面标题</title>'
                '<style>.a{color:red}</style></head>'
                '<body><script>var x=1;</script>'
                '<h1>正文标题</h1><p>第一段内容。</p><p>第二段内容。</p>'
                '</body></html>')
        fake = mock.Mock()
        fake.read.return_value = html.encode('utf-8')
        fake.__enter__ = lambda s: fake
        fake.__exit__ = lambda s, *a: False
        with mock.patch('net.urlopen',
                        return_value=fake):
            kid = knowledge.import_url('https://example.com/a')
        item = knowledge.get(kid)
        self.assertEqual(item['title'], '页面标题')
        self.assertIn('第一段内容', item['content'])
        self.assertNotIn('var x=1', item['content'])
        self.assertNotIn('color:red', item['content'])
        self.assertEqual(item['source_url'], 'https://example.com/a')


class PromptInjectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('data', exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_prompt_injects_relevant_knowledge(self):
        import ai_writer
        knowledge.add('Fable 5 定价', '输入 $5/M tokens')
        prompt = ai_writer.build_prompt({'title': 'Fable 5 发布解读',
                                         'type': '新闻解读'})
        self.assertIn('参考知识', prompt)
        self.assertIn('$5/M tokens', prompt)

    def test_build_prompt_without_knowledge_has_no_section(self):
        import ai_writer
        prompt = ai_writer.build_prompt({'title': '没有任何积累的主题',
                                         'type': '教程'})
        self.assertNotIn('参考知识', prompt)


if __name__ == '__main__':
    unittest.main()
