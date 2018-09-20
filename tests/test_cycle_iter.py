import unittest
from copy import copy

from haka_mqtt.cycle_iter import IntegralCycleIter


class TestIterCycles(unittest.TestCase):
    def test_cycle(self):
        it = IntegralCycleIter(0, 5)
        it_copy = iter(it)
        self.assertEqual(id(it), id(it_copy))
        numbers = []
        while len(numbers) < 14:
            numbers.append(next(it))

        self.assertEqual(numbers, list(range(0, 5)) + list(range(0, 5)) + list(range(0, 4)))

    def test_repeat(self):
        it = IntegralCycleIter(0, 1)
        numbers = []
        while len(numbers) < 4:
            numbers.append(next(it))

        self.assertEqual(numbers, [0]*4)

    def test_copy(self):
        it = IntegralCycleIter(0, 3)
        numbers = [next(it), next(it)]
        it_copy = copy(it)
        numbers.extend([next(it), next(it)])
        copy_numbers = [next(it_copy), next(it_copy)]

        self.assertEqual(numbers, [0, 1, 2, 0])
        self.assertEqual(copy_numbers, [2, 0])
