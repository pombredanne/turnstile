# Copyright 2013 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import unittest2

from turnstile import limits
from turnstile import utils


class TestMakeUnits(unittest2.TestCase):
    def test_make_units(self):
        result = limits._make_units(
            (1, ('a', 'b', 'c')),
            (2, ('d', 'e')),
            (3, ('f',)),
        )

        self.assertEqual(result, {
            1: 'a',
            'a': 1,
            'b': 1,
            'c': 1,
            2: 'd',
            'd': 2,
            'e': 2,
            3: 'f',
            'f': 3,
        })


class TestTimeUnit(unittest2.TestCase):
    def test_time_unit(self):
        for unit in ('second', 'seconds', 'secs', 'sec', 's', '1', 1):
            result = limits.TimeUnit(unit)
            self.assertEqual(result.value, 1)
            self.assertEqual(str(result), 'second')
            self.assertEqual(int(result), 1)

        for unit in ('minute', 'minutes', 'mins', 'min', 'm', '60', 60):
            result = limits.TimeUnit(unit)
            self.assertEqual(result.value, 60)
            self.assertEqual(str(result), 'minute')
            self.assertEqual(int(result), 60)

        for unit in ('hour', 'hours', 'hrs', 'hr', 'h', '3600', 3600):
            result = limits.TimeUnit(unit)
            self.assertEqual(result.value, 3600)
            self.assertEqual(str(result), 'hour')
            self.assertEqual(int(result), 3600)

        for unit in ('day', 'days', 'd', '86400', 86400):
            result = limits.TimeUnit(unit)
            self.assertEqual(result.value, 86400)
            self.assertEqual(str(result), 'day')
            self.assertEqual(int(result), 86400)

        for unit in ('31337', 31337):
            result = limits.TimeUnit(unit)
            self.assertEqual(result.value, 31337)
            self.assertEqual(str(result), '31337')
            self.assertEqual(int(result), 31337)

        self.assertRaises(ValueError, limits.TimeUnit, 3133.7)
        self.assertRaises(ValueError, limits.TimeUnit, -31337)
        self.assertRaises(ValueError, limits.TimeUnit, '-31337')
        self.assertRaises(ValueError, limits.TimeUnit, 'nosuchunit')


class TestBucketKey(unittest2.TestCase):
    def test_part_encode(self):
        self.assertEqual(limits.BucketKey._encode('this is a test'),
                         '"this is a test"')
        self.assertEqual(limits.BucketKey._encode(123), '123')
        self.assertEqual(limits.BucketKey._encode("don't / your %s."),
                         '"don\'t %2f your %25s."')
        self.assertEqual(limits.BucketKey._encode('you said "hello".'),
                         '"you said \\"hello\\"."')

    def test_part_decode(self):
        self.assertEqual(limits.BucketKey._decode('"this is a test"'),
                         'this is a test')
        self.assertEqual(limits.BucketKey._decode('123'), 123)
        self.assertEqual(limits.BucketKey._decode('"don\'t %2f your %25s."'),
                         "don't / your %s.")
        self.assertEqual(limits.BucketKey._decode('"you said \\"hello\\"."'),
                         'you said "hello".')

    def test_init_noversion(self):
        self.assertRaises(ValueError, limits.BucketKey, 'fake_uuid', {},
                          version=-1)

    def test_key_version1_noparams(self):
        key = limits.BucketKey('fake_uuid', {}, version=1)

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, {})
        self.assertEqual(key.version, 1)
        self.assertEqual(key._cache, None)

        expected = 'bucket:fake_uuid'

        self.assertEqual(str(key), expected)
        self.assertEqual(key._cache, expected)

    def test_key_version1_withparams(self):
        key = limits.BucketKey('fake_uuid', dict(a=1, b="2"), version=1)

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, dict(a=1, b="2"))
        self.assertEqual(key.version, 1)
        self.assertEqual(key._cache, None)

        expected = 'bucket:fake_uuid/a=1/b="2"'

        self.assertEqual(str(key), expected)
        self.assertEqual(key._cache, expected)

    def test_key_version2_noparams(self):
        key = limits.BucketKey('fake_uuid', {})

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, {})
        self.assertEqual(key.version, 2)
        self.assertEqual(key._cache, None)

        expected = 'bucket_v2:fake_uuid'

        self.assertEqual(str(key), expected)
        self.assertEqual(key._cache, expected)

    def test_key_version2_withparams(self):
        key = limits.BucketKey('fake_uuid', dict(a=1, b="2"))

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, dict(a=1, b="2"))
        self.assertEqual(key.version, 2)
        self.assertEqual(key._cache, None)

        expected = 'bucket_v2:fake_uuid/a=1/b="2"'

        self.assertEqual(str(key), expected)
        self.assertEqual(key._cache, expected)

    def test_decode_unprefixed(self):
        self.assertRaises(ValueError, limits.BucketKey.decode, 'unprefixed')

    def test_decode_badversion(self):
        self.assertRaises(ValueError, limits.BucketKey.decode, 'bad:fake_uuid')

    def test_decode_version1_noparams(self):
        key = limits.BucketKey.decode('bucket:fake_uuid')

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, {})
        self.assertEqual(key.version, 1)

    def test_decode_version1_withparams(self):
        key = limits.BucketKey.decode('bucket:fake_uuid/a=1/b="2"')

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, dict(a=1, b="2"))
        self.assertEqual(key.version, 1)

    def test_decode_version1_badparams(self):
        self.assertRaises(ValueError, limits.BucketKey.decode,
                          'bucket:fake_uuid/a=1/b="2"/c')

    def test_decode_version2_noparams(self):
        key = limits.BucketKey.decode('bucket_v2:fake_uuid')

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, {})
        self.assertEqual(key.version, 2)

    def test_decode_version2_withparams(self):
        key = limits.BucketKey.decode('bucket_v2:fake_uuid/a=1/b="2"')

        self.assertEqual(key.uuid, 'fake_uuid')
        self.assertEqual(key.params, dict(a=1, b="2"))
        self.assertEqual(key.version, 2)

    def test_decode_version2_badparams(self):
        self.assertRaises(ValueError, limits.BucketKey.decode,
                          'bucket_v2:fake_uuid/a=1/b="2"/c')


class TestBucketLoader(unittest2.TestCase):
    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_read_no_bucket_records(self, mock_loads):
        bucket_class = mock.Mock(return_value='bucket')
        records = []

        loader = limits.BucketLoader(bucket_class, 'db', 'limit', 'key',
                                     records)

        self.assertFalse(mock_loads.called)
        bucket_class.assert_called_once_with('db', 'limit', 'key')
        self.assertEqual(loader.bucket, 'bucket')
        self.assertEqual(loader.updates, 0)
        self.assertEqual(loader.delay, None)
        self.assertEqual(loader.summarized, False)
        self.assertEqual(loader.last_summarize, None)

    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_read_one_bucket_record(self, mock_loads):
        bucket_class = mock.Mock(**{'hydrate.return_value': 'bucket'})
        records = [
            dict(bucket='a bucket'),
        ]

        loader = limits.BucketLoader(bucket_class, 'db', 'limit', 'key',
                                     records)

        mock_loads.assert_called_once_with(records[0])
        bucket_class.hydrate.assert_called_once_with(
            'db', 'a bucket', 'limit', 'key')
        self.assertEqual(loader.bucket, 'bucket')
        self.assertEqual(loader.updates, 0)
        self.assertEqual(loader.delay, None)
        self.assertEqual(loader.summarized, False)
        self.assertEqual(loader.last_summarize, None)

    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_read_one_update_record(self, mock_loads):
        bucket = mock.Mock(**{'delay.return_value': None})
        bucket_class = mock.Mock(return_value=bucket)
        records = [
            dict(update=dict(params='params', time='time')),
        ]

        loader = limits.BucketLoader(bucket_class, 'db', 'limit', 'key',
                                     records)

        mock_loads.assert_called_once_with(records[0])
        bucket_class.assert_called_once_with('db', 'limit', 'key')
        bucket.delay.assert_called_once_with('params', 'time')
        self.assertEqual(loader.bucket, bucket)
        self.assertEqual(loader.updates, 1)
        self.assertEqual(loader.delay, None)
        self.assertEqual(loader.summarized, False)
        self.assertEqual(loader.last_summarize, None)

    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_read_multi_update_record(self, mock_loads):
        bucket = mock.Mock(**{'delay.return_value': None})
        bucket_class = mock.Mock(return_value=bucket)
        records = [
            dict(update=dict(params='params0', time='time0')),
            dict(update=dict(params='params1', time='time1')),
            dict(update=dict(params='params2', time='time2'), uuid='stop'),
            dict(bucket='a bucket'),
            dict(update=dict(params='params3', time='time3')),
        ]

        loader = limits.BucketLoader(bucket_class, 'db', 'limit', 'key',
                                     records, stop_uuid='stop')

        mock_loads.assert_has_calls([mock.call(rec) for rec in records])
        bucket_class.assert_called_once_with('db', 'limit', 'key')
        self.assertFalse(bucket_class.hydrate.called)
        bucket.delay.assert_has_calls([
            mock.call('params0', 'time0'),
            mock.call('params1', 'time1'),
            mock.call('params2', 'time2'),
        ])
        self.assertEqual(bucket.delay.call_count, 3)
        self.assertEqual(loader.bucket, bucket)
        self.assertEqual(loader.updates, 3)
        self.assertEqual(loader.delay, None)
        self.assertEqual(loader.summarized, False)
        self.assertEqual(loader.last_summarize, None)

    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_read_multi_update_record_traverse_summarize(self, mock_loads):
        bucket = mock.Mock(**{'delay.return_value': None})
        bucket_class = mock.Mock(return_value=bucket)
        records = [
            dict(update=dict(params='params0', time='time0')),
            dict(update=dict(params='params1', time='time1')),
            dict(summarize=True),
            dict(update=dict(params='params2', time='time2'), uuid='stop'),
            dict(bucket='a bucket'),
            dict(update=dict(params='params3', time='time3')),
        ]

        loader = limits.BucketLoader(bucket_class, 'db', 'limit', 'key',
                                     records, stop_uuid='stop')

        mock_loads.assert_has_calls([mock.call(rec) for rec in records])
        bucket_class.assert_called_once_with('db', 'limit', 'key')
        self.assertFalse(bucket_class.hydrate.called)
        bucket.delay.assert_has_calls([
            mock.call('params0', 'time0'),
            mock.call('params1', 'time1'),
            mock.call('params2', 'time2'),
        ])
        self.assertEqual(bucket.delay.call_count, 3)
        self.assertEqual(loader.bucket, bucket)
        self.assertEqual(loader.updates, 3)
        self.assertEqual(loader.delay, None)
        self.assertEqual(loader.summarized, True)
        self.assertEqual(loader.last_summarize, None)

    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_read_multi_update_record_no_traverse_summarize(self, mock_loads):
        bucket = mock.Mock(**{'delay.return_value': None})
        bucket_class = mock.Mock(return_value=bucket)
        records = [
            dict(update=dict(params='params0', time='time0')),
            dict(update=dict(params='params1', time='time1')),
            dict(update=dict(params='params2', time='time2'), uuid='stop'),
            dict(bucket='a bucket'),
            dict(summarize=True),
            dict(update=dict(params='params3', time='time3')),
        ]

        loader = limits.BucketLoader(bucket_class, 'db', 'limit', 'key',
                                     records, stop_uuid='stop')

        mock_loads.assert_has_calls([mock.call(rec) for rec in records])
        bucket_class.assert_called_once_with('db', 'limit', 'key')
        self.assertFalse(bucket_class.hydrate.called)
        bucket.delay.assert_has_calls([
            mock.call('params0', 'time0'),
            mock.call('params1', 'time1'),
            mock.call('params2', 'time2'),
        ])
        self.assertEqual(bucket.delay.call_count, 3)
        self.assertEqual(loader.bucket, bucket)
        self.assertEqual(loader.updates, 3)
        self.assertEqual(loader.delay, None)
        self.assertEqual(loader.summarized, True)
        self.assertEqual(loader.last_summarize, None)

    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_read_multi_summarize(self, mock_loads):
        bucket = mock.Mock(**{'delay.return_value': None})
        bucket_class = mock.Mock(return_value=bucket)
        records = [
            dict(update=dict(params='params0', time='time0')),
            dict(summarize=True),
            dict(update=dict(params='params1', time='time1')),
            dict(summarize=True),
            dict(update=dict(params='params2', time='time2')),
            dict(summarize=True),
            dict(update=dict(params='params3', time='time3')),
        ]

        loader = limits.BucketLoader(bucket_class, 'db', 'limit', 'key',
                                     records, stop_summarize=True)

        mock_loads.assert_has_calls([mock.call(rec) for rec in records])
        bucket_class.assert_called_once_with('db', 'limit', 'key')
        self.assertFalse(bucket_class.hydrate.called)
        bucket.delay.assert_has_calls([
            mock.call('params0', 'time0'),
            mock.call('params1', 'time1'),
            mock.call('params2', 'time2'),
        ])
        self.assertEqual(bucket.delay.call_count, 3)
        self.assertEqual(loader.bucket, bucket)
        self.assertEqual(loader.updates, 3)
        self.assertEqual(loader.delay, None)
        self.assertEqual(loader.summarized, True)
        self.assertEqual(loader.last_summarize, 5)

    @mock.patch('msgpack.loads', side_effect=lambda x: x)
    def test_need_summary(self, mock_loads):
        loader = limits.BucketLoader(mock.Mock(), 'db', 'limit', 'key', [])
        loader.updates = 5

        self.assertFalse(loader.need_summary(10))
        self.assertTrue(loader.need_summary(5))
        self.assertTrue(loader.need_summary(4))

        loader.summarized = True

        self.assertFalse(loader.need_summary(10))
        self.assertFalse(loader.need_summary(5))
        self.assertFalse(loader.need_summary(4))


class TestBucket(unittest2.TestCase):
    def test_init(self):
        bucket = limits.Bucket('db', 'limit', 'key')

        self.assertEqual(bucket.db, 'db')
        self.assertEqual(bucket.limit, 'limit')
        self.assertEqual(bucket.key, 'key')
        self.assertEqual(bucket.last, None)
        self.assertEqual(bucket.next, None)
        self.assertEqual(bucket.level, 0.0)

    def test_hydrate(self):
        bucket_dict = dict(last=1000000.0 - 3600,
                           next=1000000.0, level=0.5)
        bucket = limits.Bucket.hydrate('db', bucket_dict, 'limit', 'key')

        self.assertEqual(bucket.db, 'db')
        self.assertEqual(bucket.limit, 'limit')
        self.assertEqual(bucket.key, 'key')
        self.assertEqual(bucket.last, bucket_dict['last'])
        self.assertEqual(bucket.next, bucket_dict['next'])
        self.assertEqual(bucket.level, bucket_dict['level'])

    def test_dehydrate(self):
        bucket_dict = dict(last=1000000.0 - 3600,
                           next=1000000.0, level=0.5)
        bucket = limits.Bucket('db', 'limit', 'key', **bucket_dict)
        newdict = bucket.dehydrate()

        self.assertEqual(bucket_dict, newdict)

    @mock.patch('time.time', return_value=1000000.0)
    def test_delay_initial(self, mock_time):
        limit = mock.Mock(cost=10.0, unit_value=100)
        bucket = limits.Bucket('db', limit, 'key')
        result = bucket.delay({})

        self.assertEqual(result, None)
        self.assertEqual(bucket.last, 1000000.0)
        self.assertEqual(bucket.next, 1000000.0)
        self.assertEqual(bucket.level, 10.0)

    @mock.patch('time.time', return_value=1000000.0)
    def test_delay_expired(self, mock_time):
        limit = mock.Mock(cost=10.0, unit_value=100)
        bucket = limits.Bucket('db', limit, 'key', last=999990.0, level=10.0)
        result = bucket.delay({})

        self.assertEqual(result, None)
        self.assertEqual(bucket.last, 1000000.0)
        self.assertEqual(bucket.next, 1000000.0)
        self.assertEqual(bucket.level, 10.0)

    @mock.patch('time.time', return_value=1000000.0)
    def test_delay_overlap(self, mock_time):
        limit = mock.Mock(cost=10.0, unit_value=100)
        bucket = limits.Bucket('db', limit, 'key', last=999995.0, level=10.0)
        result = bucket.delay({})

        self.assertEqual(result, None)
        self.assertEqual(bucket.last, 1000000.0)
        self.assertEqual(bucket.next, 1000000.0)
        self.assertEqual(bucket.level, 15.0)

    @mock.patch('time.time', return_value=1000000.0)
    def test_delay_overlimit(self, mock_time):
        limit = mock.Mock(cost=10.0, unit_value=100)
        bucket = limits.Bucket('db', limit, 'key', last=999995.0, level=100.0)
        result = bucket.delay({})

        self.assertEqual(result, 5.0)
        self.assertEqual(bucket.last, 1000000.0)
        self.assertEqual(bucket.next, 1000005.0)
        self.assertEqual(bucket.level, 95.0)

    @mock.patch('time.time', return_value=1000000.0)
    def test_delay_overlimit_withnow(self, mock_time):
        limit = mock.Mock(cost=10.0, unit_value=100)
        bucket = limits.Bucket('db', limit, 'key', last=1000000.0, level=100.0)
        result = bucket.delay({}, now=1000005.0)

        self.assertEqual(result, 5.0)
        self.assertEqual(bucket.last, 1000005.0)
        self.assertEqual(bucket.next, 1000010.0)
        self.assertEqual(bucket.level, 95.0)

    @mock.patch('time.time', return_value=1000000.0)
    def test_delay_overlimit_withnow_timetravel(self, mock_time):
        limit = mock.Mock(cost=10.0, unit_value=100)
        bucket = limits.Bucket('db', limit, 'key', last=1000010.0, level=100.0)
        result = bucket.delay({}, now=1000005.0)

        self.assertEqual(result, 10.0)
        self.assertEqual(bucket.last, 1000010.0)
        self.assertEqual(bucket.next, 1000020.0)
        self.assertEqual(bucket.level, 100.0)

    @mock.patch('time.time', return_value=1000000.0)
    def test_delay_undereps(self, mock_time):
        limit = mock.Mock(cost=10.0, unit_value=100)
        bucket = limits.Bucket('db', limit, 'key', last=999995.0, level=95.1)
        result = bucket.delay({})

        self.assertEqual(result, None)
        self.assertEqual(bucket.last, 1000000.0)
        self.assertEqual(bucket.next, 1000000.0)
        self.assertEqual(bucket.level, 100.1)

    def test_messages_empty(self):
        limit = mock.Mock(unit_value=1.0, value=10)
        bucket = limits.Bucket('db', limit, 'key')

        self.assertEqual(bucket.messages, 10)

    def test_messages_half(self):
        limit = mock.Mock(unit_value=1.0, value=10)
        bucket = limits.Bucket('db', limit, 'key', level=0.5)

        self.assertEqual(bucket.messages, 5)

    def test_messages_full(self):
        limit = mock.Mock(unit_value=1.0, value=10)
        bucket = limits.Bucket('db', limit, 'key', level=1.0)

        self.assertEqual(bucket.messages, 0)

    def test_expire(self):
        bucket = limits.Bucket('db', 'limit', 'key', last=1000000.2,
                               level=5.2)

        self.assertEqual(bucket.expire, 1000006)


class LimitTest1(limits.Limit):
    pass


class LimitTest2(limits.Limit):
    attrs = dict(test_attr=dict(
            desc='Test attribute.',
            type=(str,),
            default=''))

    def route(self, uri, route_args):
        route_args['route_add'] = 'LimitTest2'
        return 'mod_%s' % uri

    def filter(self, environ, params, unused):
        if 'defer' in environ:
            raise limits.DeferLimit
        environ['test.filter.unused'] = unused
        params['filter_add'] = 'LimitTest2_direct'
        return dict(additional='LimitTest2_additional')


class TestLimitMeta(unittest2.TestCase):
    def test_registry(self):
        expected = {
            'turnstile.limits:Limit': limits.Limit,
            'tests.unit.test_limits:LimitTest1': LimitTest1,
            'tests.unit.test_limits:LimitTest2': LimitTest2,
            }

        self.assertEqual(limits.LimitMeta._registry, expected)

    def test_full_name(self):
        self.assertEqual(LimitTest1._limit_full_name,
                         'tests.unit.test_limits:LimitTest1')
        self.assertEqual(LimitTest2._limit_full_name,
                         'tests.unit.test_limits:LimitTest2')

    def test_attrs(self):
        base_attrs = set(['uuid', 'uri', 'value', 'unit', 'verbs',
                          'requirements', 'queries', 'use', 'continue_scan'])

        self.assertEqual(set(limits.Limit.attrs.keys()), base_attrs)
        self.assertEqual(set(LimitTest1.attrs.keys()), base_attrs)
        self.assertEqual(set(LimitTest2.attrs.keys()),
                         base_attrs | set(['test_attr']))