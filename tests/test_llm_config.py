import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import ai_writer
import intel_rss
import llm_config

SAMPLE = {
    'write': {'model': 'glm-5.1',
              'env': {'ANTHROPIC_AUTH_TOKEN': 'tok-w',
                      'ANTHROPIC_BASE_URL': 'https://gw.example/api'}},
    'score': {'model': 'glm-5-turbo',
              'env': {'ANTHROPIC_AUTH_TOKEN': 'tok-s',
                      'ANTHROPIC_BASE_URL': 'https://gw.example/api'}},
}


class LlmConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('data', exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_config(self, cfg=SAMPLE):
        with open(llm_config.CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)

    def test_missing_file_falls_back_to_default(self):
        cfg = llm_config.task_config('write')
        self.assertEqual(cfg['model'], '')
        self.assertIsNone(cfg['env'])

    def test_loads_task_model_and_merges_env(self):
        self._write_config()
        cfg = llm_config.task_config('score')
        self.assertEqual(cfg['model'], 'glm-5-turbo')
        self.assertEqual(cfg['env']['ANTHROPIC_AUTH_TOKEN'], 'tok-s')
        self.assertEqual(cfg['env']['ANTHROPIC_BASE_URL'],
                         'https://gw.example/api')
        # 是合并而不是替换：父进程环境要保留（PATH 没了 claude 都找不到）
        self.assertIn('PATH', cfg['env'])

    def test_unknown_task_falls_back(self):
        self._write_config()
        cfg = llm_config.task_config('nonexistent')
        self.assertEqual(cfg['model'], '')
        self.assertIsNone(cfg['env'])

    def test_broken_json_falls_back(self):
        with open(llm_config.CONFIG_PATH, 'w', encoding='utf-8') as f:
            f.write('{broken')
        cfg = llm_config.task_config('write')
        self.assertEqual(cfg['model'], '')
        self.assertIsNone(cfg['env'])


class WriterUsesConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('data', exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_passes_model_and_env(self):
        with open(llm_config.CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(SAMPLE, f)
        fake = mock.Mock(returncode=0, stdout='# 文章', stderr='')
        ai_writer._jobs['job1'] = {'status': 'running', 'article': '',
                                   'error': ''}
        with mock.patch('ai_writer.subprocess.run',
                        return_value=fake) as run:
            ai_writer._run('job1', 'prompt', os.path.join(self.tmp, 'o.md'))
        cmd = run.call_args[0][0]
        self.assertIn('--model', cmd)
        self.assertEqual(cmd[cmd.index('--model') + 1], 'glm-5.1')
        env = run.call_args[1]['env']
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'tok-w')

    def test_run_without_config_keeps_defaults(self):
        fake = mock.Mock(returncode=0, stdout='# 文章', stderr='')
        ai_writer._jobs['job2'] = {'status': 'running', 'article': '',
                                   'error': ''}
        with mock.patch('ai_writer.subprocess.run',
                        return_value=fake) as run:
            ai_writer._run('job2', 'prompt', os.path.join(self.tmp, 'o.md'))
        cmd = run.call_args[0][0]
        self.assertNotIn('--model', cmd)
        self.assertIsNone(run.call_args[1]['env'])


class ScoreUsesConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('data', exist_ok=True)
        with open(intel_rss.ITEMS_PATH, 'w', encoding='utf-8') as f:
            json.dump({'rss-a': {'id': 'rss-a', 'title': 'T', 'summary': 's',
                                 'score': None, 'fetched_at': 0}}, f)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_score_prefers_llm_config_over_score_model(self):
        with open(llm_config.CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(SAMPLE, f)
        fake = mock.Mock(returncode=0, stdout='[88]', stderr='')
        with mock.patch('intel_rss.subprocess.run',
                        return_value=fake) as run:
            intel_rss.score_pending(model='haiku')
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index('--model') + 1], 'glm-5-turbo')
        env = run.call_args[1]['env']
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'tok-s')

    def test_score_falls_back_to_score_model(self):
        fake = mock.Mock(returncode=0, stdout='[88]', stderr='')
        with mock.patch('intel_rss.subprocess.run',
                        return_value=fake) as run:
            intel_rss.score_pending(model='haiku')
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index('--model') + 1], 'haiku')
        self.assertIsNone(run.call_args[1]['env'])


if __name__ == '__main__':
    unittest.main()
