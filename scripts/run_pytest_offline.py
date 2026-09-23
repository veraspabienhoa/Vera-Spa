"""Run regression tests with outbound connections disabled; allow local test DBs."""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo


def _allowed(address):
    return isinstance(address, tuple) and address[0] in {'127.0.0.1', '::1', 'localhost'}


def _connect(sock, address):
    if not _allowed(address):
        raise OSError('External network disabled during offline tests')
    return _original_connect(sock, address)


def _connect_ex(sock, address):
    if not _allowed(address):
        raise OSError('External network disabled during offline tests')
    return _original_connect_ex(sock, address)


def _getaddrinfo(host, *args, **kwargs):
    if host not in {'127.0.0.1', '::1', 'localhost', b'127.0.0.1', b'::1', b'localhost', None}:
        raise OSError('External DNS disabled during offline tests')
    return _original_getaddrinfo(host, *args, **kwargs)


if __name__ == '__main__':
    socket.getaddrinfo = _getaddrinfo
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    raise SystemExit(pytest.main(sys.argv[1:]))
