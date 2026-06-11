import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import wechat_pub


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.skill_dir = os.path.join(self.tmp, 'baoyu-post-to-wechat')
        os.makedirs(os.path.join(self.skill_dir, 'scripts'), exist_ok=True)
        self.skill_patch = mock.patch('wechat_pub.SKILL_DIR', self.skill_dir)
        self.skill_patch.start()
        with open('a.md', 'w', encoding='utf-8') as f:
            f.write('# T\n\n正文')

    def tearDown(self):
        self.skill_patch.stop()
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_skill_dir_raises_readable_error(self):
        with mock.patch('wechat_pub.SKILL_DIR', '/nonexistent/skill'):
            with self.assertRaises(RuntimeError) as ctx:
                wechat_pub.build_command('a.md')
            self.assertIn('baoyu-post-to-wechat', str(ctx.exception))

    def test_missing_md_file_raises(self):
        with self.assertRaises(RuntimeError):
            wechat_pub.build_command('content/none.md')

    def test_api_mode_when_creds_present(self):
        with mock.patch('wechat_pub._has_api_creds', return_value=True):
            cmd, mode = wechat_pub.build_command('a.md')
        self.assertEqual(mode, 'api')
        self.assertIn('wechat-api.ts', ' '.join(cmd))
        self.assertIn('a.md', cmd)

    def test_browser_mode_without_creds(self):
        with mock.patch('wechat_pub._has_api_creds', return_value=False):
            cmd, mode = wechat_pub.build_command('a.md')
        self.assertEqual(mode, 'browser')
        joined = ' '.join(cmd)
        self.assertIn('wechat-article.ts', joined)
        self.assertIn('--markdown', cmd)
        self.assertIn('--submit', cmd)

    def test_html_mode_passes_html_flag_and_title(self):
        with open('a.html', 'w', encoding='utf-8') as f:
            f.write('<p>styled</p>')
        with mock.patch('wechat_pub._has_api_creds', return_value=False):
            cmd, mode = wechat_pub.build_command('a.html', html=True,
                                                 title='我的标题')
        self.assertEqual(mode, 'browser')
        self.assertIn('--html', cmd)
        self.assertNotIn('--markdown', cmd)
        self.assertEqual(cmd[cmd.index('--title') + 1], '我的标题')
        self.assertIn('--submit', cmd)

    def test_html_mode_api_path_keeps_title(self):
        with open('a.html', 'w', encoding='utf-8') as f:
            f.write('<p>styled</p>')
        with mock.patch('wechat_pub._has_api_creds', return_value=True):
            cmd, mode = wechat_pub.build_command('a.html', html=True,
                                                 title='我的标题')
        self.assertEqual(mode, 'api')
        self.assertIn('wechat-api.ts', ' '.join(cmd))
        self.assertIn('a.html', cmd)
        self.assertEqual(cmd[cmd.index('--title') + 1], '我的标题')


class JobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.skill_dir = os.path.join(self.tmp, 'baoyu-post-to-wechat')
        os.makedirs(os.path.join(self.skill_dir, 'scripts'), exist_ok=True)
        self.skill_patch = mock.patch('wechat_pub.SKILL_DIR', self.skill_dir)
        self.skill_patch.start()
        with open('a.md', 'w', encoding='utf-8') as f:
            f.write('# T\n\n正文')

    def tearDown(self):
        self.skill_patch.stop()
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait(self, job_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = wechat_pub.get_job(job_id)
            if job['status'] != 'running':
                return job
            time.sleep(0.02)
        self.fail('job did not finish')

    def test_publish_success_flow(self):
        done = {}
        fake = mock.Mock(returncode=0, stdout='draft created', stderr='')
        with mock.patch('wechat_pub.subprocess.run', return_value=fake), \
             mock.patch('wechat_pub._has_api_creds', return_value=True):
            job_id = wechat_pub.start_publish(
                'a.md', on_finish=lambda s, e: done.update(s=s, e=e))
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'done')
        self.assertEqual(job['mode'], 'api')
        self.assertEqual(done['s'], 'done')

    def test_publish_failure_records_error(self):
        fake = mock.Mock(returncode=1, stdout='',
                         stderr='Missing WECHAT_APP_ID')
        with mock.patch('wechat_pub.subprocess.run', return_value=fake), \
             mock.patch('wechat_pub._has_api_creds', return_value=True):
            job_id = wechat_pub.start_publish('a.md')
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'error')
        self.assertIn('WECHAT_APP_ID', job['error'])

    def test_get_job_unknown_returns_none(self):
        self.assertIsNone(wechat_pub.get_job('nope'))


if __name__ == '__main__':
    unittest.main()
