from time import time


class SystemClock(object):
    def time(self):
        return time()


class SettableClock(object):
    def __init__(self):
        self.__time = 0

    def add_time(self, duration):
        self.__time += duration

    def set_time(self, t):
        self.__time = t

    def time(self):
        return self.__time