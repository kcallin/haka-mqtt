from haka_mqtt.cycle_iter import IntegralCycleIter
from haka_mqtt.exception import PacketIdReactorException


class PacketIdGenerator(object):
    def __init__(self, ids=[]):
        self.__packet_id_iter = IntegralCycleIter(0, self.max_len())
        self.__consumed_ids = set(ids)

    @staticmethod
    def max_len():
        return 2**16

    def __len__(self):
        """Returns number of packet ids that have been consumed.

        Returns
        -------
        int
        """
        return len(self.__consumed_ids)

    def __iter__(self):
        return iter(self.__consumed_ids)

    def acquire(self):
        """
        Raises
        ------
        haka_mqtt.exception.PacketIdReactorException
            Raised when there are no packet ids remaining to be
            acquired.

        Returns
        -------
        int
            A `packet_id` such that 0 <= `packet_id` <= 2**16-1.
        """
        for i in xrange(0, 2**16):
            n = next(self.__packet_id_iter)
            if n not in self.__consumed_ids:
                self.__consumed_ids.add(n)
                break
        else:
            raise PacketIdReactorException()

        return n

    def release(self, packet_id):
        """
        Parameters
        -----------
        packet_id: int
            A `packet_id` that has been previously acquired and is to
            be returned to the set.

        Raises
        ------
        KeyError
            Raised when there are no packet ids remaining to be
            acquired.
        """
        self.__consumed_ids.remove(packet_id)
