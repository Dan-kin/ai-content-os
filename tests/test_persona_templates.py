import json
import os
import shutil
import tempfile
import unittest

import ai_writer
import persona


class TmpDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp)


class PersonaTest(TmpDirTest):
    def test_load_defaults_when_no_file(self):
        p = persona.load()
        self.assertEqual(p, persona.DEFAULTS)
        self.assertTrue(persona.is_empty(p))

    def test_save_and_load_roundtrip(self):
        saved = persona.save({'tone': '犀利', 'taboo': '赋能',
                              'unknown_key': 'x'})
        self.assertEqual(saved['tone'], '犀利')
        self.assertNotIn('unknown_key', saved)
        loaded = persona.load()
        self.assertEqual(loaded['tone'], '犀利')
        self.assertEqual(loaded['taboo'], '赋能')
        self.assertFalse(persona.is_empty(loaded))


class TemplatesTest(TmpDirTest):
    def test_builtin_guides_without_file(self):
        guides = ai_writer.type_guides()
        self.assertIn('新闻解读', guides)
        self.assertEqual(len(guides), len(ai_writer.TYPE_GUIDES))

    def test_custom_templates_override_and_extend(self):
        os.makedirs('data')
        with open('data/templates.json', 'w', encoding='utf-8') as f:
            json.dump({'新闻解读': '自定义指引',
                       '爆款清单': '列 N 个工具，每个给出场景'}, f,
                      ensure_ascii=False)
        guides = ai_writer.type_guides()
        self.assertEqual(guides['新闻解读'], '自定义指引')
        self.assertEqual(guides['爆款清单'], '列 N 个工具，每个给出场景')
        prompt = ai_writer.build_prompt({'title': 'T', 'type': '爆款清单'})
        self.assertIn('列 N 个工具', prompt)

    def test_broken_templates_file_falls_back(self):
        os.makedirs('data')
        with open('data/templates.json', 'w', encoding='utf-8') as f:
            f.write('{broken json')
        guides = ai_writer.type_guides()
        self.assertEqual(guides, ai_writer.TYPE_GUIDES)


if __name__ == '__main__':
    unittest.main()
