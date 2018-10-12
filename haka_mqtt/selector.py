
class Selector(object):
    def __init__(self):
        pass

    def add_read(self, fd, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        pass

    def del_read(self, fd, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        pass

    def add_write(self, f, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        pass

    def del_write(self, fd, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        pass
