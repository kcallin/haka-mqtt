import fcntl
import os
import socket
import threading
from Queue import Queue, Empty
from time import sleep


class _Future(object):
    def __init__(self):
        self.__cancelled = False
        self.__done = False
        self.__result = None
        self.__exception = None
        self.__notified = False
        self.__callbacks = []
        self._thread = None

    def _notify(self):
        if not self.__notified:
            self.__notified = True
            for cb in self.__callbacks:
                cb(self)

    def cancel(self):
        if self.done():
            rv = False
        else:
            self.__cancelled = True
            self.__done = True
            self._notify()
            rv = True

        return rv

    def set_result(self, result):
        """
        Sets the result of the work associated with the Future to result.

        This method should only be used by Executor implementations and unit tests.
        """
        assert not self.done()
        self.__result = result
        self.__done = True

    def set_exception(self, exception):
        """
            Sets the result of the work associated with the Future to the Exception exception.

            This method should only be used by Executor implementations and unit tests.
        """
        assert not self.done()
        self.__exception = exception
        self.__done = True

    def cancelled(self):
        return self.__cancelled

    def done(self):
        return self.__done

    def result(self, timeout=None):
        return self.__result

    def exception(self, timeout=None):
        return self.__exception

    def add_done_callback(self, fn):
        if self.done():
            fn(self)
        else:
            self.__callbacks.append(fn)


def call_task(queue, wd, future, callable, *args, **kwargs):
    """

    Parameters
    ----------
    queue: Queue
    wd: fileno
    future: _Future
    params: tuple
    """
    try:
        rv = callable(*args, **kwargs)
        future.set_result(rv)
        queue.put(future)
    except socket.gaierror as e:
        future.set_exception(e)
        queue.put(future)

    while True:
        num_bytes_written = os.write(wd, 'x')
        if num_bytes_written == 1:
            break
        elif num_bytes_written == 0:
            sleep(0.01)
        else:
            raise NotImplementedError(num_bytes_written)


class AsyncFutureDnsResolver(object):
    """This class is not thread safe; it must be accessed from one
    thread only.
    """
    def __init__(self):
        self.__enable = True
        self.__queue = Queue()
        self.__threads = []
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

    def close(self):
        self.__enable = False
        self.join()
        os.close(self.__wd)
        os.close(self.__rd)

    def __call__(self, host, port, family=0, socktype=0, proto=0, flags=0):
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

        Returns
        -------
        Future
            If the DNS lookup succeeds then the `future.result()` will
            immediately return a 5-tuple with a structure like
            (family, socktype, proto, canonname, sockaddr).  On failure
            then `future.exception()` will immediately return a
            `socket.gaierror`.

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
        assert self.__enable, 'Async dns lookup after resolver closed.'

        future = _Future()
        getadrrinfo_params = (host, port, family, socktype, proto, flags)
        thread_args = (self.__queue, self.__wd, future, socket.getaddrinfo) + getadrrinfo_params
        t = threading.Thread(target=call_task, args=thread_args)
        future._thread = t
        self.__threads.append(t)
        t.start()

        return future

    def read_fd(self):
        """int: fileno"""
        return self.__rd

    def poll(self):
        if os.read(self.__rd, 1):
            try:
                future = self.__queue.get_nowait()
            except Empty:
                pass
            else:
                self.__threads.remove(future._thread)
                future._notify()

    def join(self):
        for thread in self.__threads:
            thread.join()
