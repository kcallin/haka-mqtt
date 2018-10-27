import socket
import ssl


class SocketFactory(object):
    def __init__(self):
        pass

    def __call__(self, addr):
        if len(addr) == 2:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif len(addr) == 4:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            raise NotImplementedError(addr)

        sock.setblocking(False)
        return sock


class SslSocketFactory(object):
    def __init__(self, context, hostname):
        """

        Parameters
        ----------
        context: ssl.SSLContext
        hostname: str
        """
        self.__context = context
        self.__hostname = hostname

    def __call__(self, addr):
        """
        Returns
        -------
        ssl.SSLSocket
        """

        if len(addr) == 2:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif len(addr) == 4:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            raise NotImplementedError(addr)

        sock = self.__context.wrap_socket(sock,
                                          server_side=False,
                                          do_handshake_on_connect=False,
                                          suppress_ragged_eofs=True,
                                          server_hostname=self.__hostname)
        sock.setblocking(False)
        return sock
