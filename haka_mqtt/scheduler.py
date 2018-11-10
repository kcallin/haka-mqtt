from bisect import insort_right, bisect_left


class Deadline(object):
    def __init__(self, deadline_entry):
        self.__deadline_entry = deadline_entry

    def expired(self):
        """bool: True if callback has already been called; False
        otherwise."""
        return self.__deadline_entry.expired

    def cancel(self):
        """Stops a scheduled callback from being made; has no effect if
        cancel is called after the callback has already been made."""
        self.__deadline_entry.cancel()


class _DeadlineEntry(object):
    def __init__(self, instant, queue, cb):
        self.instant = instant
        self.cb = cb
        self.queue = queue
        self.expired = False

    def cancel(self):
        if not self.expired:
            self.expired = True
            idx = bisect_left(self.queue, self)
            while idx < len(self.queue):
                if id(self.queue[idx]) == id(self):
                    del self.queue[idx]
                    break
                elif self.queue[idx] > self:
                    raise AssertionError()
                else:
                    idx += 1

    def __eq__(self, other):
        return self.instant == other.instant

    def __ne__(self, other):
        return self.instant != other.instant

    def __lt__(self, other):
        return self.instant < other.instant

    def __gt__(self, other):
        return self.instant > other.instant

    def __le__(self, other):
        return self.instant <= other.instant

    def __ge__(self, other):
        return self.instant >= other.instant


class Scheduler(object):
    def __init__(self):
        self._queue = []

    def instant(self):
        """Returns the current tick.

        Returns
        -------
        int
        """
        raise NotImplementedError()

    def remaining(self):
        """Duration remaining to next scheduled callback.

        Returns
        -------
        int or None
        """
        if self._queue:
            rv = self._queue[0].instant - self.instant()
        else:
            rv = None

        return rv

    def add(self, duration, cb):
        """Adds `duration` to `self.instant()` and calls all scheduled
        callbacks.

        Parameters
        ----------
        duration: int
            Number of ticks passed.
        cb: callable()
            No calling with so

        Returns
        -------
        Deadline
        """
        de = _DeadlineEntry(self.instant() + duration, self._queue, cb)
        insort_right(self._queue, de)
        return Deadline(de)

    def __len__(self):
        return len(self._queue)


class DurationScheduler(Scheduler):
    def __init__(self):
        Scheduler.__init__(self)
        self._instant = 0
        self._queue = []

    def instant(self):
        """Returns the current tick.

        Returns
        -------
        int
        """
        return self._instant

    def poll(self, duration):
        """Adds `duration` to `self.instant()` and calls all scheduled
        callbacks.

        Parameters
        ----------
        duration: int
        """
        self._instant += duration

        while self._queue and self._queue[0].instant <= self.instant():
            de = self._queue.pop(0)
            de.expired = True
            de.cb()


class ClockScheduler(Scheduler):
    def __init__(self, clock):
        Scheduler.__init__(self)
        self.__clock = clock

    def instant(self):
        """Current clock instant.

        Returns
        -------
        int
            Current clock scheduler.
        """
        return self.__clock.time()

    def poll(self):
        """Calls all callbacks awaiting execution to this point."""
        while self._queue and self._queue[0].instant <= self.instant():
            de = self._queue.pop(0)
            de.expired = True
            de.cb()
