import socket


class SynchronousFuture(object):
    def __init__(self, result=None, exception=None):
        assert result or exception

        self.__result = result
        self.__exception = exception

    def cancel(self):
        """Always returns False since this future is finished the
        instant it is created.

        Attempt to cancel the call. If the call is currently being
        executed and cannot be cancelled then the method will return
        False, otherwise the call will be cancelled and the method will
        return True.

        Returns
        -------
        bool
        """
        return False

    def cancelled(self):
        """Always returns False since this future is finished the
        instant it is created.

        Return True if the call was successfully cancelled.

        Returns
        -------
        bool
        """
        return False

    def done(self):
        """Always returns true since this future is finished the instant
        it is created.

        Return True if the call was successfully cancelled or finished
        running.

        Returns
        -------
        bool
        """
        return True

    def result(self, timeout=None):
        """Immediately returns the call resultor None if the call
        raised an exception.

        Return the value returned by the call. If the call hasn't yet
        completed then this method will wait up to timeout seconds. If
        the call hasn't completed in timeout seconds, then a
        concurrent.futures.TimeoutError will be raised. timeout can be
        an int or float. If timeout is not specified or None, there is
        no limit to the wait time.

        If the future is cancelled before completing then
        CancelledError will be raised.

        If the call raised, this method will raise the
        same exception.
        """
        return self.__result

    def exception(self, timeout=None):
        """Immediately returns the exception raised by the call or None
        if the call completed without raising.

        Return the exception raised by the call. If the call hasn't yet
        completed then this method will wait up to timeout seconds. If
        the call hasn't completed in timeout seconds, then a
        concurrent.futures.TimeoutError will be raised. timeout can be
        an int or float. If timeout is not specified or None, there is
        no limit to the wait time.

        If the future is cancelled before completing then CancelledError
        will be raised.

        If the call completed without raising, None is returned.
        """
        return self.__exception

    def add_done_callback(self, fn):
        """
        Attaches the callable fn to the future. fn will be called, with
        the future as its only argument, when the future is cancelled
        or finishes running.

        Added callables are called in the order that they were added and
        are always called in a thread belonging to the process that
        added them. If the callable raises an Exception subclass, it
        will be logged and ignored. If the callable raises a
        BaseException subclass, the behavior is undefined.

        If the future has already completed or been cancelled, fn will
        be called immediately.
        """
        fn(self)


class SynchronousFutureDnsResolver(object):
    def __init__(self):
        pass

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
        SynchronousFuture
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
        try:
            result = socket.getaddrinfo(host, port, family, socktype, proto, flags)
            exception = None
        except socket.gaierror as exception:
            result = None

        return SynchronousFuture(result, exception)
