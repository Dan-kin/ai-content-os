import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import intel
import store


def _fake_response(payload):
    body = json.dumps(payload).encode('utf-8')

    class FakeRes(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    return FakeRes(body)


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp)

    def test_fetch_uses_browser_ua_and_caches(self):
        payload = {'items': [{'id': 'a1', 'title': 'X', 'url': 'https://x',
                              'score': 80, 'category': 'industry'}]}
        with mock.patch('intel.urllib.request.urlopen',
                        return_value=_fake_response(payload)) as m:
            items, cached = intel.fetch_items(hours=24)
            self.assertFalse(cached)
            self.assertEqual(items[0]['id'], 'a1')
            req = m.call_args[0][0]
            self.assertIn('Mozilla', req.get_header('User-agent', ''))
            self.assertIn('mode=selected', req.full_url)

        # 第二次相同参数：走缓存，不再发请求
        with mock.patch('intel.urllib.request.urlopen') as m2:
            items2, cached2 = intel.fetch_items(hours=24)
            self.assertTrue(cached2)
            self.assertEqual(items2[0]['id'], 'a1')
            m2.assert_not_called()

    def test_fetch_param_combinations_have_separate_cache(self):
        p1 = {'items': [{'id': 'a1'}]}
        p2 = {'items': [{'id': 'b2'}]}
        with mock.patch('intel.urllib.request.urlopen',
                        side_effect=[_fake_response(p1), _fake_response(p2)]):
            items1, _ = intel.fetch_items(hours=24)
            items2, _ = intel.fetch_items(hours=24, category='paper')
        self.assertNotEqual(items1[0]['id'], items2[0]['id'])


class AdoptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.item = {'id': 'it1', 'title': 'Fable 5 发布',
                     'url': 'https://example.com/a',
                     'summary': '新模型发布', 'score': 92,
                     'category': 'ai-models'}

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp)

    def test_adopt_creates_topic_with_source_and_verify_note(self):
        topic_id, existed = intel.adopt(self.item)
        self.assertFalse(existed)
        topics = store.list_topics()
        self.assertEqual(len(topics), 1)
        t = topics[0]
        self.assertEqual(t['id'], topic_id)
        self.assertEqual(t['title'], 'Fable 5 发布')
        self.assertEqual(t['source'], 'https://example.com/a')
        self.assertEqual(t['type'], '新闻解读')
        self.assertIn('新模型发布', t['notes'])
        self.assertIn('92', t['notes'])
        self.assertIn('核实', t['notes'])

    def test_adopt_twice_returns_existing_topic(self):
        topic_id1, existed1 = intel.adopt(self.item)
        topic_id2, existed2 = intel.adopt(self.item)
        self.assertFalse(existed1)
        self.assertTrue(existed2)
        self.assertEqual(topic_id1, topic_id2)
        self.assertEqual(len(store.list_topics()), 1)

    def test_adopt_requires_id_or_url(self):
        with self.assertRaises(ValueError):
            intel.adopt({'title': 'x'})

    def test_category_mapping(self):
        self.assertEqual(intel._category_to_type('paper'), '技术拆解')
        self.assertEqual(intel._category_to_type('tip'), '教程')
        self.assertEqual(intel._category_to_type('unknown'), '新闻解读')


if __name__ == '__main__':
    unittest.main()
