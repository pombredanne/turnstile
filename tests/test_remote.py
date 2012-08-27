import errno
import json
import socket
import time

import eventlet

from turnstile import remote

import tests


class FakeSocket(object):
    def __init__(self, *msgs, **kwargs):
        self._send_data = []
        self._recv_data = []
        self._actions = []
        self._fail = kwargs.get('fail')
        self._clients = kwargs.get('clients', [])
        self._closed = False

        if msgs:
            self._recv_data.extend(msgs)

    def _check_closed(self):
        if self._closed:
            raise socket.error(errno.EBADF, 'Bad file descriptor')

    def close(self):
        self._check_closed()
        self._closed = True

    def sendall(self, msg):
        self._check_closed()
        self._send_data.append(msg)

    def recv(self, size):
        self._check_closed()
        if not self._recv_data:
            self._closed = True
            return ''
        return self._recv_data.pop(0)

    def setsockopt(self, *args, **kwargs):
        self._actions.append(('setsockopt', args, kwargs))
        if self._fail == 'setsockopt':
            raise socket.error("setsockopt error occurred")

    def bind(self, *args, **kwargs):
        self._actions.append(('bind', args, kwargs))
        if self._fail == 'bind':
            raise socket.error("bind error occurred")

    def listen(self, *args, **kwargs):
        self._actions.append(('listen', args, kwargs))
        if self._fail == 'listen':
            raise socket.error("listen error occurred")

    def accept(self):
        if not self._clients:
            raise socket.error("out of clients")
        tmp = self._clients.pop(0)
        if isinstance(tmp, Exception):
            raise tmp
        return tmp, ('localhost', 1023)


class TestConnection(tests.TestCase):
    def test_send_open(self):
        sock = FakeSocket()
        conn = remote.Connection(sock)

        conn.send('FOO', 'Nobody', 'inspects', 'the', 'spammish', 'repetition')

        self.assertEqual(sock._send_data, [
                '{"cmd": "FOO", "payload": ["Nobody", "inspects", "the", '
                '"spammish", "repetition"]}\n'
                ])

    def test_send_closed(self):
        conn = remote.Connection(None)

        self.assertRaises(remote.ConnectionClosed, conn.send,
                          'FOO', 'Nobody', 'inspects', 'the', 'spammish',
                          'repetition')

    def test_send_error(self):
        sock = FakeSocket()
        sock.close()  # Make it raise an error
        conn = remote.Connection(sock)

        self.assertRaises(socket.error, conn.send, 'FOO', 'Nobody',
                          'inspects', 'the', 'spammish', 'repetition')
        self.assertEqual(conn._sock, None)

    def test_recvbuf_pop_msg(self):
        conn = remote.Connection(None)
        conn._recvbuf.append(dict(cmd='FOO', payload=['Nobody', 'inspects',
                                                      'the', 'spammish',
                                                      'repetition']))
        result = conn._recvbuf_pop()

        self.assertEqual(result, ('FOO', ['Nobody', 'inspects', 'the',
                                          'spammish', 'repetition']))

    def test_recvbuf_pop_exc(self):
        conn = remote.Connection(None)
        conn._recvbuf.append(Exception())
        self.assertRaises(Exception, conn._recvbuf_pop)

    def test_close(self):
        sock = FakeSocket()
        conn = remote.Connection(sock)
        conn._recvbuf.append('foo')
        conn._recvbuf_partial = 'bar'

        conn.close()

        self.assertTrue(sock._closed)
        self.assertEqual(conn._sock, None)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, '')

    def test_close_double(self):
        conn = remote.Connection(None)
        conn._recvbuf.append('foo')
        conn._recvbuf_partial = 'bar'

        conn.close()

        self.assertEqual(conn._sock, None)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, '')

    def stub_recvbuf_pop(self):
        def fake_recvbuf_pop(self):
            # I don't want to bother putting real messages on the
            # queue
            return self._recvbuf.pop(0)

        self.stubs.Set(remote.Connection, '_recvbuf_pop', fake_recvbuf_pop)
        self.stubs.Set(json, 'loads', lambda x: x)

    def test_recv_recvbuf_filled(self):
        self.stub_recvbuf_pop()

        conn = remote.Connection(None)
        conn._recvbuf = ['foo', 'bar']

        result = conn.recv()

        self.assertEqual(result, 'foo')
        self.assertEqual(conn._recvbuf, ['bar'])

    def test_recv_recvbuf_empty_closed(self):
        self.stub_recvbuf_pop()

        conn = remote.Connection(None)

        self.assertRaises(remote.ConnectionClosed, conn.recv)

    def test_recv_onemsg(self):
        self.stub_recvbuf_pop()

        sock = FakeSocket('foobar\n')
        conn = remote.Connection(sock)

        result = conn.recv()

        self.assertEqual(result, 'foobar')
        self.assertEqual(conn._sock, sock)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, '')

    def test_recv_onemsg_existing_partial(self):
        self.stub_recvbuf_pop()

        sock = FakeSocket('bar\n')
        conn = remote.Connection(sock)
        conn._recvbuf_partial = 'foo'

        result = conn.recv()

        self.assertEqual(result, 'foobar')
        self.assertEqual(conn._sock, sock)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, '')

    def test_recv_onemsg_onepartial(self):
        self.stub_recvbuf_pop()

        sock = FakeSocket('bar\nfoo')
        conn = remote.Connection(sock)

        result = conn.recv()

        self.assertEqual(result, 'bar')
        self.assertEqual(conn._sock, sock)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, 'foo')

    def test_recv_multimsg(self):
        self.stub_recvbuf_pop()

        sock = FakeSocket('foo\nbar\nbaz\n')
        conn = remote.Connection(sock)

        result = conn.recv()

        self.assertEqual(result, 'foo')
        self.assertEqual(conn._sock, sock)
        self.assertEqual(conn._recvbuf, ['bar', 'baz'])
        self.assertEqual(conn._recvbuf_partial, '')

    def test_recv_longmsg(self):
        self.stub_recvbuf_pop()

        sock = FakeSocket('foo', 'bar', 'baz\n')
        conn = remote.Connection(sock)

        result = conn.recv()

        self.assertEqual(result, 'foobarbaz')
        self.assertEqual(conn._sock, sock)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, '')

    def test_recv_closed(self):
        self.stub_recvbuf_pop()

        sock = FakeSocket('foo')
        conn = remote.Connection(sock)

        self.assertRaises(remote.ConnectionClosed, conn.recv)
        self.assertEqual(conn._sock, None)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, '')

    def test_recv_error(self):
        self.stub_recvbuf_pop()

        sock = FakeSocket()
        sock.close()  # Make it raise an error
        conn = remote.Connection(sock)

        self.assertRaises(socket.error, conn.recv)
        self.assertEqual(conn._sock, None)
        self.assertEqual(conn._recvbuf, [])
        self.assertEqual(conn._recvbuf_partial, '')


class FakeConnection(object):
    def __init__(self, msgs=None):
        self._sendbuf = []
        self._recvbuf = msgs or []
        self._closed = False

    def _check_closed(self):
        if self._closed:
            raise remote.ConnectionClosed("Connection closed")

    def close(self):
        self._closed = True

    def send(self, cmd, *payload):
        self._check_closed()
        self._sendbuf.append(dict(cmd=cmd, payload=payload))

    def recv(self):
        msg = self._recvbuf.pop(0)
        if isinstance(msg, Exception):
            raise msg
        return msg['cmd'], msg['payload']


# Used for testing @remote
class FakeSimpleRPC(object):
    def __init__(self, mode, msgs=None):
        self.mode = mode
        self.conn = None
        self._msgs = msgs
        self._closed = False

    def close(self):
        self._closed = True

    def connect(self):
        self.conn = FakeConnection(self._msgs)

    @remote.remote
    def foobar(self, *args, **kwargs):
        assert self.mode == 'server'
        return args, kwargs


class TestException(Exception):
    pass


class TestRemote(tests.TestCase):
    imports = {
        'TestException': TestException,
        }

    def test_remote_attribute(self):
        rpc = FakeSimpleRPC(None)

        self.assertTrue(hasattr(rpc.foobar, '_remote'))
        self.assertTrue(rpc.foobar._remote)

    def test_remote_server(self):
        rpc = FakeSimpleRPC('server')

        result = rpc.foobar(1, 2, 3, a=4, b=5, c=6)

        self.assertEqual(result, ((1, 2, 3), dict(a=4, b=5, c=6)))
        self.assertEqual(rpc.conn, None)

    def test_remote_result(self):
        rpc = FakeSimpleRPC('client', [dict(cmd='RES', payload=['foobar'])])

        result = rpc.foobar(1, 2, 3, a=4, b=5, c=6)

        self.assertEqual(result, 'foobar')
        self.assertNotEqual(rpc.conn, None)
        self.assertEqual(rpc.conn._sendbuf, [
                dict(
                    cmd='CALL',
                    payload=('foobar', (1, 2, 3), dict(a=4, b=5, c=6)),
                    )])
        self.assertFalse(rpc._closed)

    def test_remote_complex_result(self):
        rpc = FakeSimpleRPC('client', [dict(cmd='RES', payload=[(3, 2, 1)])])

        result = rpc.foobar(1, 2, 3, a=4, b=5, c=6)

        self.assertEqual(result, (3, 2, 1))
        self.assertNotEqual(rpc.conn, None)
        self.assertEqual(rpc.conn._sendbuf, [
                dict(
                    cmd='CALL',
                    payload=('foobar', (1, 2, 3), dict(a=4, b=5, c=6)),
                    )])
        self.assertFalse(rpc._closed)

    def test_remote_exception(self):
        rpc = FakeSimpleRPC('client', [
                dict(
                    cmd='EXC',
                    payload=('TestException', 'this is a test'),
                    )])

        try:
            rpc.foobar()
            self.fail("Failed to raise TestException")
        except TestException as exc:
            self.assertEqual(str(exc), 'this is a test')
        self.assertFalse(rpc._closed)

    def test_remote_error(self):
        rpc = FakeSimpleRPC('client', [dict(cmd='ERR', payload=('wassup?',))])

        try:
            rpc.foobar()
            self.fail("Failed to raise Exception")
        except Exception as exc:
            self.assertEqual(str(exc),
                             'Catastrophic error from server: wassup?')
        self.assertTrue(rpc._closed)

    def test_remote_invalid(self):
        rpc = FakeSimpleRPC('client', [dict(cmd='FOO', payload=('wassup?',))])

        try:
            rpc.foobar()
            self.fail("Failed to raise Exception")
        except Exception as exc:
            self.assertEqual(str(exc),
                             "Invalid command response from server: FOO")
        self.assertTrue(rpc._closed)


class TestCreateServer(tests.TestCase):
    def setUp(self):
        super(TestCreateServer, self).setUp()

        self.socks = []

        def fake_getaddrinfo(host, port, family, socktype):
            # Use comma-separated hosts
            if host:
                for h in host.split(','):
                    yield (h, socktype, 'tcp', '', (host, int(port)))

        def fake_socket(family, type_, proto):
            self.assertEqual(type_, socket.SOCK_STREAM)
            self.assertEqual(proto, 'tcp')

            # Fail if family is 'fail'
            if family == 'fail':
                raise socket.error("failed to get socket")

            kwargs = {}
            if family in ('setsockopt', 'bind', 'listen'):
                kwargs['fail'] = family

            # Get a fake socket
            sock = FakeSocket(**kwargs)
            self.socks.append(sock)

            return sock

        self.stubs.Set(socket, 'getaddrinfo', fake_getaddrinfo)
        self.stubs.Set(socket, 'socket', fake_socket)

    def test_noaddrs(self):
        try:
            remote._create_server('', '1023')
            self.fail("_create_server() failed to raise socket.error")
        except socket.error as exc:
            self.assertEqual(str(exc), 'getaddrinfo returns an empty list')
        self.assertEqual(self.socks, [])

    def test_fails(self):
        try:
            remote._create_server('fail,setsockopt,bind,listen', '1023')
            self.fail("_create_server() failed to raise socket.error")
        except socket.error as exc:
            self.assertEqual(str(exc), 'listen error occurred')

        self.assertEqual(len(self.socks), 3)
        for idx, failtype in enumerate(('setsockopt', 'bind', 'listen')):
            self.assertEqual(self.socks[idx]._fail, failtype)
            self.assertEqual(self.socks[idx]._closed, True)

    def test_succeeds(self):
        sock = remote._create_server('localhost', '1023')

        self.assertEqual(self.socks, [sock])
        self.assertEqual(sock._actions, [
                ('setsockopt', (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
                 {}),
                ('bind', (('localhost', 1023),), {}),
                ('listen', (1024,), {}),
                ])
        self.assertEqual(sock._closed, False)


class RPCforTest(remote.SimpleRPC):
    connection_class = FakeConnection


class TestSimpleRPC(tests.TestCase):
    def setUp(self):
        super(TestSimpleRPC, self).setUp()

        self.msgs = []
        self.addr = None

        def fake_create_connection(addr):
            self.addr = addr
            return self.msgs

        self.stubs.Set(socket, 'create_connection', fake_create_connection)

    def test_init(self):
        rpc = RPCforTest('localhost', 'port', 'authkey')

        self.assertEqual(rpc.host, 'localhost')
        self.assertEqual(rpc.port, 'port')
        self.assertEqual(rpc.authkey, 'authkey')
        self.assertEqual(rpc.mode, None)
        self.assertEqual(rpc.conn, None)

    def test_close(self):
        conn = FakeConnection()
        rpc = RPCforTest('localhost', 'port', 'authkey')
        rpc.conn = conn

        rpc.close()

        self.assertEqual(rpc.conn, None)
        self.assertEqual(conn._closed, True)

    def test_close_redundant(self):
        rpc = RPCforTest('localhost', 'port', 'authkey')

        rpc.close()

        self.assertEqual(rpc.conn, None)

    def test_connect_server(self):
        rpc = RPCforTest('localhost', 'port', 'authkey')
        rpc.mode = 'server'

        self.assertRaises(ValueError, rpc.connect)
        self.assertEqual(rpc.mode, 'server')

    def test_connect_redundant(self):
        rpc = RPCforTest('localhost', 'port', 'authkey')
        rpc.mode = 'client'
        rpc.conn = 'connected'

        rpc.connect()

        self.assertEqual(rpc.mode, 'client')
        self.assertEqual(rpc.conn, 'connected')

    def test_connect_authed(self):
        self.msgs.append(dict(cmd='OK', payload=()))

        rpc = RPCforTest('localhost', 'port', 'authkey')

        rpc.connect()

        self.assertEqual(rpc.mode, 'client')
        self.assertNotEqual(rpc.conn, None)
        self.assertEqual(rpc.conn._sendbuf,
                         [dict(cmd='AUTH', payload=('authkey',))])

    def test_connect_err(self):
        self.msgs.append(dict(cmd='ERR', payload=('failed to auth',)))

        rpc = RPCforTest('localhost', 'port', 'authkey')

        rpc.connect()

        self.assertEqual(rpc.mode, 'client')
        self.assertEqual(rpc.conn, None)
        self.assertEqual(self.log_messages, [
                "Failed to authenticate to localhost port port: "
                "failed to auth",
                ])

    def test_connect_valueerror(self):
        self.msgs.append(ValueError("Bogus message"))

        rpc = RPCforTest('localhost', 'port', 'authkey')

        self.assertRaises(ValueError, rpc.connect)
        self.assertEqual(rpc.mode, 'client')
        self.assertEqual(rpc.conn, None)
        self.assertEqual(self.log_messages, [
                "Received bogus response from server: Bogus message",
                ])

    def test_connect_connectionclosed(self):
        self.msgs.append(remote.ConnectionClosed("Connection closed"))

        rpc = RPCforTest('localhost', 'port', 'authkey')

        self.assertRaises(remote.ConnectionClosed, rpc.connect)
        self.assertEqual(rpc.mode, 'client')
        self.assertEqual(rpc.conn, None)
        self.assertEqual(self.log_messages, [
                "Connection closed while authenticating to server",
                ])

    def test_connect_otherexception(self):
        self.msgs.append(TestException("foobar"))

        rpc = RPCforTest('localhost', 'port', 'authkey')

        self.assertRaises(TestException, rpc.connect)
        self.assertEqual(rpc.mode, 'client')
        self.assertEqual(rpc.conn, None)
        self.assertEqual(len(self.log_messages), 1)
        self.assertTrue(self.log_messages[0].startswith(
                "Failed to authenticate to server"))

    def stub_for_connect(self):
        conn = FakeConnection(self.msgs)

        def fake_connect(inst):
            inst.conn = conn

        self.stubs.Set(RPCforTest, 'connect', fake_connect)

        return conn

    def test_ping(self):
        cur_time = time.time()

        def fake_time():
            return cur_time

        self.stubs.Set(time, 'time', fake_time)

        self.msgs.append(dict(cmd='PONG', payload=(cur_time - 60,)))
        conn = self.stub_for_connect()

        rpc = RPCforTest('localhost', 'port', 'authkey')

        result = rpc.ping()

        self.assertEqual(result, 60.0)
        self.assertEqual(rpc.conn, conn)
        self.assertEqual(conn._sendbuf,
                         [dict(cmd='PING', payload=(cur_time,))])

    def test_ping_fail(self):
        self.msgs.append(dict(cmd='FOO', payload=('hi there',)))
        conn = self.stub_for_connect()

        rpc = RPCforTest('localhost', 'port', 'authkey')

        self.assertRaises(Exception, rpc.ping)

    def test_listen_client(self):
        rpc = RPCforTest('localhost', 'port', 'authkey')
        rpc.mode = 'client'

        self.assertRaises(ValueError, rpc.listen)
        self.assertEqual(rpc.mode, 'client')

    def test_listen(self):
        listen_sock = FakeSocket(clients=[None, Exception('foo'), None])

        def fake_create_server(host, port):
            return listen_sock

        def fake_spawn_n(serve, conn, addr):
            self.assertEqual(serve.im_class, RPCforTest)
            self.assertIsInstance(conn, FakeConnection)
            self.assertEqual(addr, ('localhost', 1023))

        self.stubs.Set(remote, '_create_server', fake_create_server)
        self.stubs.Set(eventlet, 'spawn_n', fake_spawn_n)

        rpc = RPCforTest('localhost', 'port', 'authkey')

        rpc.listen()

        self.assertEqual(rpc.mode, 'server')
        self.assertEqual(rpc.conn, None)
        self.assertEqual(len(self.log_messages), 3)
        self.assertEqual(self.log_messages[0],
                         'Accepted connection from localhost port 1023')
        self.assertEqual(self.log_messages[1],
                         'Accepted connection from localhost port 1023')
        self.assertTrue(self.log_messages[2].startswith(
                'Too many errors accepting connections: out of clients'))
        self.assertEqual(listen_sock._closed, True)
