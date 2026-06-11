import os
import shutil
import tempfile
import unittest

import store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp)

    def test_create_and_list(self):
        t = store.create_topic('Fable 5 发布解读', type='新闻解读',
                               source='https://example.com')
        self.assertEqual(t['status'], '待调研')
        topics = store.list_topics()
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]['title'], 'Fable 5 发布解读')

    def test_create_requires_title(self):
        with self.assertRaises(ValueError):
            store.create_topic('   ')

    def test_update_status(self):
        t = store.create_topic('测试选题')
        updated = store.update_topic(t['id'], status='待写作')
        self.assertEqual(updated['status'], '待写作')

    def test_update_rejects_bad_status(self):
        t = store.create_topic('测试选题')
        with self.assertRaises(ValueError):
            store.update_topic(t['id'], status='乱写的')

    def test_update_missing_topic(self):
        with self.assertRaises(KeyError):
            store.update_topic('nope', status='待写作')

    def test_delete(self):
        t = store.create_topic('要删除的选题')
        store.delete_topic(t['id'])
        self.assertEqual(store.list_topics(), [])
        with self.assertRaises(KeyError):
            store.delete_topic(t['id'])


if __name__ == '__main__':
    unittest.main()
