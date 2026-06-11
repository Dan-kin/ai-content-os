import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import rewriter


class PromptTest(unittest.TestCase):
    def test_build_prompt_includes_article_and_user_feedback(self):
        prompt = rewriter.build_prompt(
            '# 原标题\n\n正文',
            modes=['hook', 'deai', 'examples'],
            instructions='我觉得第二节太空，请补一个职场例子。')
        self.assertIn('重写开头', prompt)
        self.assertIn('去掉 AI 味', prompt)
        self.assertIn('补具体例子', prompt)
        self.assertIn('第二节太空', prompt)
        self.assertIn('# 原标题', prompt)


class OutputPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('content')

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_output_path_creates_revised_copy_without_overwrite(self):
        first = rewriter.output_path('content/a.md')
        self.assertEqual(first, 'content/a-revised.md')
        open(first, 'w').close()
        second = rewriter.output_path('content/a.md')
        self.assertEqual(second, 'content/a-revised-2.md')


class RewriteJobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('content')
        with open('content/a.md', 'w', encoding='utf-8') as f:
            f.write('# 原文\n\n正文')

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait(self, job_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = rewriter.get_job(job_id)
            if job['status'] != 'running':
                return job
            time.sleep(0.02)
        self.fail('job did not finish')

    def test_rewrite_writes_new_file(self):
        with mock.patch('llm_client.generate_text', return_value='# 新稿\n\n更好正文') as gen:
            job_id = rewriter.start_rewrite(
                'content/a.md', modes=['deai'], instructions='更像公众号')
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'done')
        self.assertEqual(job['output'], 'content/a-revised.md')
        with open(job['output'], encoding='utf-8') as f:
            self.assertIn('更好正文', f.read())
        self.assertIn('更像公众号', gen.call_args[0][1])

    def test_rewrite_failure_records_error(self):
        with mock.patch('llm_client.generate_text', side_effect=RuntimeError('boom')):
            job_id = rewriter.start_rewrite('content/a.md')
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'error')
        self.assertIn('boom', job['error'])


if __name__ == '__main__':
    unittest.main()
