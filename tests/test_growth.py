import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import growth
import llm_config


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('data', exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_and_list(self):
        rec = growth.add_record('content/a.md', '公众号',
                                read=1200, like=45, share=12, comment=8)
        self.assertTrue(rec['id'])
        self.assertTrue(rec['noted_at'])
        records = growth.list_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['read'], 1200)
        self.assertEqual(records[0]['platform'], '公众号')

    def test_add_requires_article(self):
        with self.assertRaises(ValueError):
            growth.add_record('', '公众号')

    def test_counts_are_normalized_to_int(self):
        rec = growth.add_record('content/a.md', '知乎', read='300',
                                like='', share=None, comment='5')
        self.assertEqual(rec['read'], 300)
        self.assertEqual(rec['like'], 0)
        self.assertEqual(rec['share'], 0)
        self.assertEqual(rec['comment'], 5)

    def test_delete(self):
        rec = growth.add_record('content/a.md', '公众号', read=10)
        growth.delete_record(rec['id'])
        self.assertEqual(growth.list_records(), [])


class AnalyzeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs('data', exist_ok=True)
        growth.add_record('content/a.md', '公众号', read=5000, like=200)
        growth.add_record('content/b.md', '公众号', read=300, like=5)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait(self, job_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = growth.get_job(job_id)
            if job['status'] != 'running':
                return job
            time.sleep(0.02)
        self.fail('job did not finish')

    def test_analyze_saves_result(self):
        fake = mock.Mock(returncode=0, stdout='高赞内容的共性是…', stderr='')
        with mock.patch('llm_client.subprocess.run', return_value=fake):
            job_id = growth.start_analyze()
            job = self._wait(job_id)
        self.assertEqual(job['status'], 'done')
        saved = growth.last_analysis()
        self.assertIn('高赞内容', saved['text'])
        self.assertTrue(saved['at'])

    def test_analyze_prompt_contains_data(self):
        fake = mock.Mock(returncode=0, stdout='ok', stderr='')
        with mock.patch('llm_client.subprocess.run', return_value=fake) as run:
            job_id = growth.start_analyze()
            self._wait(job_id)
        prompt = run.call_args[0][0][2]  # claude -p <prompt>
        self.assertIn('content/a.md', prompt)
        self.assertIn('5000', prompt)

    def test_analyze_uses_growth_config_fallback_to_write(self):
        with open(llm_config.CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({'write': {'model': 'glm-5.1', 'env': {'A': 'b'}}}, f)
        fake = mock.Mock(returncode=0, stdout='ok', stderr='')
        with mock.patch('llm_client.subprocess.run', return_value=fake) as run:
            self._wait(growth.start_analyze())
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index('--model') + 1], 'glm-5.1')

    def test_analyze_without_records_raises(self):
        for r in growth.list_records():
            growth.delete_record(r['id'])
        with self.assertRaises(RuntimeError):
            growth.start_analyze()


if __name__ == '__main__':
    unittest.main()
