import doctest
import examples.frontend_poll


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(examples.frontend_poll))
    return tests
