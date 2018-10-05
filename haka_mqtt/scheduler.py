from bisect import insort_right, bisect_left


class Deadline(object):
    def __init__(self, deadline_entry):
        self.__deadline_entry = deadline_entry

    def expired(self):
        return self.__deadline_entry.expired

    def cancel(self):
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
        self.__instant = 0
        self.__queue = []

    def instant(self):
        return self.__instant

    def remaining(self):
        if self.__queue:
            rv = self.__queue[0].instant - self.instant()
        else:
            rv = None

        return rv

    def add(self, duration, cb):
        de = _DeadlineEntry(self.instant() + duration, self.__queue, cb)
        insort_right(self.__queue, de)
        return Deadline(de)

    def poll(self, duration):
        self.__instant += duration

        while self.__queue and self.__queue[0].instant <= self.instant():
            de = self.__queue.pop(0)
            de.expired = True
            de.cb()

    def __len__(self):
        return len(self.__queue)