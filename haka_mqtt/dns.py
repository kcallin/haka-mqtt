import socket
import threading
from Queue import Queue


def getaddrinfo_enqueue(queue, request_id, params):
    """

    Parameters
    ----------
    queue: Queue
    request_id: object
    params: tuple
    """
    rv = socket.getaddrinfo(*params)
    queue.put((request_id, rv))


class AsyncDnsResolver(object):
    def __init__(self, enqueue=getaddrinfo_enqueue):
        self.__queue = Queue()
        self.__request_id_to_cb = {}

    def getaddrinfo(self, on_resolution, host, port, family=0, socktype=0, proto=0, flags=0):
        """

        Parameters
        ----------
        on_resolution: callable

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
        getaddrinfo_params = (host, port, family, socktype, proto, flags)
        try:
            request_id = max(self.__request_id_to_cb) + 1
        except ValueError:
            request_id = 1
        self.__request_id_to_cb[request_id] = on_resolution
        t = threading.Thread(target=getaddrinfo_enqueue, args=(self.__queue, request_id, getaddrinfo_params))
        t.start()

    def poll(self):
        request_id, result = self.__queue.get_nowait()
        cb = self.__request_id_to_cb.pop(request_id)
        cb(result)

    def get(self):
        request_id, result = self.__queue.get()
        cb = self.__request_id_to_cb.pop(request_id)
        cb(result)
