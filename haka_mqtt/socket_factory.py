import socket
import ssl


class BlockingSocketFactory(object):
    def __init__(self):
        pass

    def __call__(self, getaddrinfo_params, addr):
        host, port, address_family, socktype, proto, flags = getaddrinfo_params

        if len(addr) == 2:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif len(addr) == 4:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            raise NotImplementedError(addr)

        sock.setblocking(True)
        return sock


class SocketFactory(object):
    def __init__(self):
        pass

    def __call__(self, getaddrinfo_params, addr):
        host, port, address_family, socktype, proto, flags = getaddrinfo_params

        if len(addr) == 2:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif len(addr) == 4:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            raise NotImplementedError(addr)

        sock.setblocking(False)
        return sock


class BlockingSslSocketFactory(object):
    def __init__(self, context):
        """

        Parameters
        ----------
        context: ssl.SSLContext
        """
        self.__context = context

    def __call__(self, getaddrinfo_params, addr):
        """
        Returns
        -------
        ssl.SSLSocket
        """

        host, port, address_family, socktype, proto, flags = getaddrinfo_params

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
                                          server_hostname=host)
        sock.setblocking(True)
        return sock


class SslSocketFactory(object):
    def __init__(self, context):
        """

        Parameters
        ----------
        context: ssl.SSLContext
        """
        self.__context = context

    def __call__(self, getaddrinfo_params, addr):
        """
        Returns
        -------
        ssl.SSLSocket
        """

        host, port, address_family, socktype, proto, flags = getaddrinfo_params

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
                                          server_hostname=host)
        sock.setblocking(False)
        return sock
