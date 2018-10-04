import socket


class SocketFactory(object):
    def __init__(self):
        pass

    def __call__(self):
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


class SslSocketFactory(object):
    def __init__(self, context, hostname):
        """

        Parameters
        ----------
        context: ssl.SSLContext
        """
        self.__context = context
        self.__hostname = hostname

    def __call__(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__context.wrap_socket(sock,
                                   server_side=False,
                                   do_handshake_on_connect=True,
                                   suppress_ragged_eofs=True,
                                   server_hostname=self.__hostname)