import socket


class SocketFactory(object):
    def __init__(self):
        pass

    def __call__(self):
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)
