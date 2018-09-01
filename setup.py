from os.path import join, dirname
from setuptools import setup, find_packages


def read_path(filename):
    with open(join(dirname(__file__), filename)) as f:
        return f.read()


setup(
    name="haka-mqtt",
    version="0.1.0",
    install_requires=[
        'enum34>=1.1.6;python_version<"3.4"',
    ],
    tests_require = [
        'mock',
    ],
    test_suite="tests",
    packages=find_packages(),
    author="Keegan Callin",
    author_email="kc@kcallin.net",
#    license="PSF",
#    keywords="hello world example examples",
#    could also include long_description, download_url, classifiers, etc.
    url="http://example.com/HelloWorld/",   # project home page
    description="Weapons grade MQTT client.",
    long_description=read_path('README.rst'),
    project_urls={
        "Bug Tracker": "https://github.com/kcallin/haka-mqtt/issues",
        "Documentation": "https://haka-mqtt.readthedocs.io/en/latest/",
        "Source Code": "https://github.com/kcallin/haka-mqtt",
    }
)

