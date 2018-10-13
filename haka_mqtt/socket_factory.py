import socket
import ssl


def socket_factory():
    """
    Returns
    -------
    socket.socket
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(0)
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

    def __call__(self):
        """
        Returns
        -------
        ssl.SSLSocket
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock = self.__context.wrap_socket(sock,
                                          server_side=False,
                                          do_handshake_on_connect=False,
                                          suppress_ragged_eofs=True,
                                          server_hostname=self.__hostname)
        sock.setblocking(0)
        return sock
