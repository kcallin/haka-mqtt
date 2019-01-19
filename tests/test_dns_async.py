import doctest
import haka_mqtt.dns_async


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(haka_mqtt.dns_async))
    return tests
