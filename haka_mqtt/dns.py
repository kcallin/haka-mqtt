import fcntl
import os
import socket
import threading
from Queue import (
    Queue,
    Empty,
)


def getaddrinfo_enqueue(queue, wd, request_id, params):
    """

    Parameters
    ----------
    queue: Queue
    wd: fileno
    request_id: object
    params: tuple
    """
    try:
        rv = socket.getaddrinfo(*params)
        queue.put((request_id, rv))
        while True:
            num_bytes_written = os.write(wd, 'x')
            if num_bytes_written == 1:
                break
    except socket.gaierror as e:
        queue.put((request_id, e))


class AsyncDnsResolver(object):
    def __init__(self, enqueue=getaddrinfo_enqueue):
        self.__queue = Queue()
        self.__request_id_to_cb = {}
        self.__closed = False
        self.__closing = False
        self.__rd, self.__wd = os.pipe()

        flags = fcntl.fcntl(self.__rd, fcntl.F_GETFL)
        fcntl.fcntl(self.__rd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        flags = fcntl.fcntl(self.__wd, fcntl.F_GETFL)
        fcntl.fcntl(self.__wd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()

    def __call__(self, host, port, family=0, socktype=0, proto=0, flags=0, callback=None):
        """

        Parameters
        ----------
        host: str or None
            A host `str` must contain either a domain name for lookup
            or a string representation of an IPv4/v6 address.
        port: str or int or None
            A string service name such as 'http', a numeric port number,
            or None.
        family: int
        socktype: int
        proto: int
        flags: int
            One or several of the AI_* constants; default is zero.
        callback: callable or None

        Returns
        -------
        list of 5-tuples
            Each 5-tuple has the structure (family, socktype, proto, canonname, sockaddr).

            In these tuples, family, socktype, proto are all integers
            and are meant to be passed to the socket() function.
            canonname will be a string representing the canonical name
            of the host if AI_CANONNAME is part of the flags argument;
            else canonname will be empty. sockaddr is a tuple
            describing a socket address, whose format depends on the
            returned family (a (address, port) 2-tuple for AF_INET, a
            (address, port, flow info, scope id) 4-tuple for AF_INET6),
            and is meant to be passed to the socket.connect() method.
        """
        if self.__closing:
            raise socket.gaierror(socket.EAI_SYSTEM, 'error.')

        getaddrinfo_params = (host, port, family, socktype, proto, flags)
        try:
            request_id = max(self.__request_id_to_cb) + 1
        except ValueError:
            request_id = 1
        self.__request_id_to_cb[request_id] = callback
        t = threading.Thread(target=getaddrinfo_enqueue, args=(self.__queue, self.__wd, request_id, getaddrinfo_params))
        t.start()

    def read_fd(self):
        """int: fileno"""
        return self.__rd

    def poll(self):
        if os.read(self.__rd, 1):
            try:
                request_id, result = self.__queue.get_nowait()
            except Empty:
                pass
            else:
                cb = self.__request_id_to_cb.pop(request_id)
                cb(result)

    def get(self):
        request_id, result = self.__queue.get()
        os.read(self.__rd, 1)
        cb = self.__request_id_to_cb.pop(request_id)
        cb(result)

    def join(self):
        while self.__request_id_to_cb:
            self.get()

    @property
    def closed(self):
        """bool: True when closed; False otherwise."""
        return self.__closed

    def close(self):
        self.__closing = True
        self.join()
        os.close(self.__wd)
        os.close(self.__rd)
        self.__closed = True


class SynchronousDnsResolver(object):
    def __init__(self):
        pass

    def __call__(self, host, port, family=0, socktype=0, proto=0, flags=0, callback=None):
        """

        Parameters
        ----------
        host: str or None
            A host `str` must contain either a domain name for lookup
            or a string representation of an IPv4/v6 address.
        port: str or int or None
            A string service name such as 'http', a numeric port number,
            or None.
        family: int
        socktype: int
        proto: int
        flags: int
            One or several of the AI_* constants; default is zero.
        callback: callable
            Ignored.

        Raises
        ------
        socket.gaierror

        Returns
        -------
        list of 5-tuples
            Each 5-tuple has the structure (family, socktype, proto, canonname, sockaddr).

            In these tuples, family, socktype, proto are all integers
            and are meant to be passed to the socket() function.
            canonname will be a string representing the canonical name
            of the host if AI_CANONNAME is part of the flags argument;
            else canonname will be empty. sockaddr is a tuple
            describing a socket address, whose format depends on the
            returned family (a (address, port) 2-tuple for AF_INET, a
            (address, port, flow info, scope id) 4-tuple for AF_INET6),
            and is meant to be passed to the socket.connect() method.
        """
        return socket.getaddrinfo(host, port, family, socktype, proto, flags)
