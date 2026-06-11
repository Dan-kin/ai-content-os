import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import dist
import llm_config


class PromptTest(unittest.TestCase):
    def test_platforms_have_templates(self):
        for p in ('zhihu', 'xhs', 'x'):
            prompt = dist.build_prompt(p, '# 标题\n\n正文内容')
            self.assertIn('正文内容', prompt)
        with self.assertRaises(ValueError):
            dist.build_prompt('weibo', 'x')

    def test_output_path_suffix_and_no_overwrite(self):
        tmp = tempfile.mkdtemp()
        old = os.getcwd()
        os.chdir(tmp)
        try:
            os.makedirs('content', exist_ok=True)
            p1 = dist.output_path('content/a.md', 'zhihu')
            self.assertEqual(p1, 'content/a-zhihu.md')
            open(p1, 'w').close()
            p2 = dist.output_path('content/a.md', 'zhihu')
            self.assertNotEqual(p1, p2)  # 已存在则换名，绝不覆盖
        finally:
            os.chdir(old)
            shutil.rmtree(tmp, ignore_errors=True)


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('content', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        with open('content/a.md', 'w', encoding='utf-8') as f:
            f.write('# 原文\n\n这是正文。')

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait(self, job_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = dist.get_job(job_id)
            if job['status'] != 'running':
                return job
            time.sleep(0.02)
        self.fail('job did not finish')

    def test_convert_writes_output_file(self):
        fake = mock.Mock(returncode=0, stdout='转换后的内容', stderr='')
        with mock.patch('dist.subprocess.run', return_value=fake):
            job_id = dist.start_convert('content/a.md', 'xhs')
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'done')
        self.assertTrue(os.path.exists(job['output']))
        with open(job['output'], encoding='utf-8') as f:
            self.assertIn('转换后的内容', f.read())

    def test_convert_uses_dist_llm_config_with_write_fallback(self):
        cfg = {'write': {'model': 'glm-5.1',
                         'env': {'ANTHROPIC_AUTH_TOKEN': 'tok'}}}
        with open(llm_config.CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        fake = mock.Mock(returncode=0, stdout='ok', stderr='')
        with mock.patch('dist.subprocess.run', return_value=fake) as run:
            job_id = dist.start_convert('content/a.md', 'zhihu')
            self._wait(job_id)
        cmd = run.call_args[0][0]
        # 没有 dist 配置时回退 write 配置
        self.assertEqual(cmd[cmd.index('--model') + 1], 'glm-5.1')
        self.assertEqual(run.call_args[1]['env']['ANTHROPIC_AUTH_TOKEN'],
                         'tok')

    def test_convert_failure_records_error(self):
        fake = mock.Mock(returncode=1, stdout='', stderr='boom')
        with mock.patch('dist.subprocess.run', return_value=fake):
            job_id = dist.start_convert('content/a.md', 'x')
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'error')
        self.assertIn('boom', job['error'])

    def test_convert_missing_file_raises(self):
        with self.assertRaises(RuntimeError):
            dist.start_convert('content/none.md', 'zhihu')


if __name__ == '__main__':
    unittest.main()
