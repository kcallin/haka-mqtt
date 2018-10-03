class IntegralCycleIter(object):
    """

    Parameters
    ----------
    start: int
    end: int
    """

    def __init__(self, start, end):
        assert start < end
        assert isinstance(start, int)
        assert isinstance(end, int)

        self.start = start
        self.end = end
        self.__next = start

    def next(self):
        """Returns the next iterator in the sequence.

        Returns
        -------
        int
        """
        n = self.__next
        if self.__next + 1 == self.end:
            self.__next = self.start
        else:
            self.__next += 1
        return n

    def __iter__(self):
        return self
