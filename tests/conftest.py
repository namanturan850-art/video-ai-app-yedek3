"""Opt-in offline execution: AVS_OFFLINE_TESTS=1 forbids real external sockets."""
import ipaddress
import os
import socket

import pytest


@pytest.fixture(autouse=True)
def offline_connections(monkeypatch):
    if os.environ.get('AVS_OFFLINE_TESTS') != '1':
        return
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple):
            host = address[0]
            try: local = ipaddress.ip_address(host).is_loopback
            except ValueError: local = host == 'localhost'
            if not local:
                raise AssertionError('Offline test attempted an external connection')
        return original(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', connect)
