import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import image_planner


VALID_PLAN_JSON = """
{
  "images": [
    {
      "id": "cover",
      "type": "cover",
      "insert_after_heading": "",
      "purpose": "用一张图建立文章主题",
      "context": "文章讨论 AI 时代人才标准",
      "visual_concept": "一个人在工具和判断力之间做选择",
      "composition": "真实职场场景，电脑屏幕和便签，柔和自然光",
      "cn_prompt": "真实职场摄影风格，一个知识工作者面对 AI 工具和决策便签",
      "en_prompt": "realistic workplace photography, a knowledge worker facing AI tools and decision notes",
      "negative_prompt": "不要文字，不要赛博朋克，不要夸张表情",
      "aspect_ratio": "16:9",
      "caption": "AI 时代，工具熟练度只是起点"
    },
    {
      "id": "image-1",
      "type": "concept",
      "insert_after_heading": "## 判断力比工具熟练更重要",
      "purpose": "解释核心观点转折",
      "context": "文章强调判断力",
      "visual_concept": "从工具列表走向判断框架",
      "composition": "干净桌面，左侧工具图标，右侧决策树便签",
      "cn_prompt": "简洁商业摄影风格，桌面上左侧是 AI 工具图标，右侧是决策树便签",
      "en_prompt": "minimal business photography, AI tool icons on the left, decision tree notes on the right",
      "negative_prompt": "不要文字，不要 logo，不要科幻蓝光",
      "aspect_ratio": "4:3",
      "caption": "真正稀缺的是判断框架"
    }
  ]
}
"""


class PromptTest(unittest.TestCase):
    def test_build_prompt_includes_article_count_and_user_direction(self):
        prompt = image_planner.build_prompt(
            '# AI 时代的人才标准\n\n正文',
            count='light',
            instructions='不要赛博风，多用真实职场场景。',
            insert_placeholders=True)
        self.assertIn('AI 时代的人才标准', prompt)
        self.assertIn('2-3 张', prompt)
        self.assertIn('不要赛博风', prompt)
        self.assertIn('JSON', prompt)
        self.assertIn('insert_after_heading', prompt)


class ParsePlanTest(unittest.TestCase):
    def test_parse_plan_accepts_json_fenced_response(self):
        plan = image_planner.parse_plan('```json\n' + VALID_PLAN_JSON + '\n```')
        self.assertEqual(len(plan['images']), 2)
        self.assertEqual(plan['images'][0]['id'], 'cover')
        self.assertEqual(plan['images'][1]['aspect_ratio'], '4:3')

    def test_parse_plan_rejects_invalid_json(self):
        with self.assertRaises(RuntimeError) as ctx:
            image_planner.parse_plan('不是 JSON')
        self.assertIn('配图规划解析失败', str(ctx.exception))


class OutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('content')
        with open('content/a.md', 'w', encoding='utf-8') as f:
            f.write('# 标题\n\n开头\n\n## 判断力比工具熟练更重要\n\n正文')

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_output_paths_do_not_overwrite_existing_files(self):
        article, prompts = image_planner.output_paths('content/a.md')
        self.assertEqual(article, 'content/a-images.md')
        self.assertEqual(prompts, 'content/a-image-prompts.md')
        open(article, 'w').close()
        open(prompts, 'w').close()
        article2, prompts2 = image_planner.output_paths('content/a.md')
        self.assertEqual(article2, 'content/a-images-2.md')
        self.assertEqual(prompts2, 'content/a-image-prompts-2.md')

    def test_insert_placeholders_matches_heading_and_appends_unmatched(self):
        plan = image_planner.parse_plan(VALID_PLAN_JSON)
        text = '# 标题\n\n开头\n\n## 判断力比工具熟练更重要\n\n正文'
        updated = image_planner.insert_placeholders(
            text, plan, 'content/a-image-prompts.md')
        self.assertIn('assets/images/a-cover.png', updated)
        self.assertIn('assets/images/a-image-1.png', updated)
        self.assertIn('## 判断力比工具熟练更重要\n\n![配图建议', updated)
        self.assertIn('content/a-image-prompts.md#image-1', updated)

    def test_render_prompt_pack_contains_cn_and_en_prompts(self):
        plan = image_planner.parse_plan(VALID_PLAN_JSON)
        pack = image_planner.render_prompt_pack('content/a.md', plan)
        self.assertIn('# AI 配图 Prompt 包', pack)
        self.assertIn('## cover', pack)
        self.assertIn('中文 Prompt', pack)
        self.assertIn('English Prompt', pack)
        self.assertIn('真实职场摄影风格', pack)


class ImagePlanJobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('content')
        with open('content/a.md', 'w', encoding='utf-8') as f:
            f.write('# 标题\n\n开头\n\n## 判断力比工具熟练更重要\n\n正文')

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait(self, job_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = image_planner.get_job(job_id)
            if job['status'] != 'running':
                return job
            time.sleep(0.02)
        self.fail('job did not finish')

    def test_start_plan_writes_article_copy_and_prompt_pack(self):
        with mock.patch('llm_client.generate_text', return_value=VALID_PLAN_JSON) as gen:
            job_id = image_planner.start_plan(
                'content/a.md',
                count='standard',
                instructions='多用真实场景',
                insert_placeholders=True)
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'done')
        self.assertEqual(job['output'], 'content/a-images.md')
        self.assertEqual(job['prompts'], 'content/a-image-prompts.md')
        with open(job['output'], encoding='utf-8') as f:
            self.assertIn('![配图建议', f.read())
        with open(job['prompts'], encoding='utf-8') as f:
            self.assertIn('English Prompt', f.read())
        self.assertEqual(gen.call_args[0][0], 'image')
        self.assertIn('多用真实场景', gen.call_args[0][1])

    def test_start_plan_failure_records_error(self):
        with mock.patch('llm_client.generate_text', side_effect=RuntimeError('boom')):
            job_id = image_planner.start_plan('content/a.md')
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'error')
        self.assertIn('boom', job['error'])


if __name__ == '__main__':
    unittest.main()
