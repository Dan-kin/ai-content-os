import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import ai_writer


class PromptTest(unittest.TestCase):
    def test_build_prompt_includes_topic_fields(self):
        topic = {'title': 'Fable 5 发布解读', 'type': '新闻解读',
                 'source': 'https://anthropic.com', 'notes': '重点对比上一代'}
        prompt = ai_writer.build_prompt(topic, length='1500',
                                        style='犀利', audience='AI 从业者')
        for fragment in ['Fable 5 发布解读', '新闻解读', 'https://anthropic.com',
                         '重点对比上一代', '1500', '犀利', 'AI 从业者']:
            self.assertIn(fragment, prompt)

    def test_build_prompt_skips_empty_optional_fields(self):
        prompt = ai_writer.build_prompt({'title': '极简选题', 'type': '教程'})
        self.assertNotIn('参考来源', prompt)
        self.assertNotIn('选题备注', prompt)
        self.assertNotIn('补充要求', prompt)
        self.assertNotIn('品牌人设', prompt)

    def test_build_prompt_injects_persona(self):
        p = {'name': '老 K', 'tone': '犀利直接', 'vocabulary': '说人话',
             'hook': '场景引入', 'cta': '关注我', 'taboo': '赋能,抓手'}
        prompt = ai_writer.build_prompt({'title': 'T', 'type': '教程'},
                                        persona=p)
        for fragment in ['品牌人设', '老 K', '犀利直接', '说人话',
                         '场景引入', '关注我', '赋能,抓手', '绝对不可出现']:
            self.assertIn(fragment, prompt)

    def test_build_prompt_skips_empty_persona(self):
        empty = {'name': '', 'tone': '', 'vocabulary': '', 'hook': '',
                 'cta': '', 'taboo': ''}
        prompt = ai_writer.build_prompt({'title': 'T', 'type': '教程'},
                                        persona=empty)
        self.assertNotIn('品牌人设', prompt)


class UniquePathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('content')

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp)

    def test_sanitizes_title(self):
        path = ai_writer.unique_path('GPT-5 vs Claude: 谁更强?')
        self.assertTrue(path.startswith('content/'))
        self.assertTrue(path.endswith('.md'))
        self.assertNotIn(':', os.path.basename(path))
        self.assertNotIn('?', path)

    def test_never_overwrites_existing_file(self):
        p1 = ai_writer.unique_path('同名选题')
        open(p1, 'w').close()
        p2 = ai_writer.unique_path('同名选题')
        self.assertNotEqual(p1, p2)


class JobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('content')

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp)

    def _wait(self, job_id):
        for _ in range(50):
            if ai_writer.get_job(job_id)['status'] != 'running':
                break
            time.sleep(0.1)
        return ai_writer.get_job(job_id)

    def test_job_success_writes_file(self):
        topic = {'id': 't1', 'title': '任务测试', 'type': '教程'}
        fake = mock.Mock(returncode=0, stdout='# 标题\n\n正文', stderr='')
        with mock.patch('llm_client.subprocess.run', return_value=fake):
            job_id, out_path = ai_writer.start_job(topic, {})
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'done')
        with open(out_path, encoding='utf-8') as f:
            self.assertIn('# 标题', f.read())

    def test_job_failure_records_error(self):
        topic = {'id': 't2', 'title': '失败测试', 'type': '教程'}
        fake = mock.Mock(returncode=1, stdout='', stderr='boom')
        with mock.patch('llm_client.subprocess.run', return_value=fake):
            job_id, _ = ai_writer.start_job(topic, {})
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'error')
        self.assertIn('boom', job['error'])

    def test_get_job_unknown_id(self):
        self.assertIsNone(ai_writer.get_job('nope'))

    def test_job_calls_on_finish(self):
        calls = []
        topic = {'id': 't3', 'title': '回调测试', 'type': '教程'}
        fake = mock.Mock(returncode=0, stdout='# ok', stderr='')
        with mock.patch('llm_client.subprocess.run', return_value=fake):
            job_id, _ = ai_writer.start_job(
                topic, {}, on_finish=lambda s, e: calls.append((s, e)))
            self._wait(job_id)
        self.assertEqual(calls, [('done', '')])

    def test_job_failure_calls_on_finish_with_error(self):
        calls = []
        topic = {'id': 't4', 'title': '回调失败测试', 'type': '教程'}
        fake = mock.Mock(returncode=1, stdout='', stderr='boom')
        with mock.patch('llm_client.subprocess.run', return_value=fake):
            job_id, _ = ai_writer.start_job(
                topic, {}, on_finish=lambda s, e: calls.append((s, e)))
            self._wait(job_id)
        self.assertEqual(calls, [('error', 'boom')])


if __name__ == '__main__':
    unittest.main()
