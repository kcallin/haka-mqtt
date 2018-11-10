import unittest

from haka_mqtt.scheduler import DurationScheduler


class Target():
    def __init__(self):
        self.set = False

    def __call__(self, *args, **kwargs):
        self.set = True


class TestScheduler(unittest.TestCase):
    def test_scheduler(self):
        s = DurationScheduler()
        self.assertIsNone(s.remaining())
        self.assertEqual(0, len(s))

        s.poll(0)
        self.assertIsNone(s.remaining())
        self.assertEqual(0, len(s))

        t0 = Target()
        t1 = Target()

        d0 = s.add(0, t0)
        self.assertEqual(1, len(s))
        self.assertEqual(0, s.remaining())
        self.assertFalse(t0.set)
        self.assertIsNotNone(d0)

        s.poll(0)
        self.assertEqual(0, len(s))
        self.assertIsNone(s.remaining())
        self.assertTrue(t0.set)

        t0 = Target()
        d1 = s.add(10, t1)
        d0 = s.add(3, t0)
        self.assertEqual(2, len(s))
        self.assertEqual(s.remaining(), 3)
        self.assertIsNotNone(d0)

        s.poll(s.remaining())
        self.assertTrue(t0.set)
        self.assertFalse(t1.set)
        self.assertEqual(s.remaining(), 7)
        self.assertEqual(1, len(s))

        d1.cancel()
        self.assertTrue(t0.set)
        self.assertFalse(t1.set)
        self.assertIsNone(s.remaining())
        self.assertEqual(0, len(s))
        self.assertTrue(d1.expired())

    def test_scheduler_0(self):
        s = DurationScheduler()
        self.assertIsNone(s.remaining())
        self.assertEqual(0, len(s))

        s.poll(0)
        self.assertIsNone(s.remaining())
        self.assertEqual(0, len(s))

        t0 = Target()
        t1 = Target()

        d0 = s.add(0, t0)
        self.assertEqual(1, len(s))
        self.assertEqual(0, s.remaining())
        self.assertFalse(t0.set)
        self.assertIsNotNone(d0)
        self.assertFalse(d0.expired())

        s.poll(s.remaining())
        self.assertTrue(d0.expired())

