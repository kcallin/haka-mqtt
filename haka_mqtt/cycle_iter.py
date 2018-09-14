class IntegralCycleIter(object):
    def __init__(self, start, end):
        """

        Parameters
        ----------
        start: int
        end: int
        """
        assert start < end
        self.start = start
        self.end = end
        self.__next = start

    def next(self):
        n = self.__next
        if self.__next + 1 == self.end:
            self.__next = self.start
        else:
            self.__next += 1
        return n

    def __iter__(self):
        return self
