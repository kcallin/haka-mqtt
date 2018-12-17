import sys
from glob import glob
from os import chdir
from os.path import join, dirname, abspath
from setuptools import setup, find_packages


def read_path(filename):
    with open(join(project_dir, filename)) as f:
        return f.read()

# Documentation on this setup function can be found at
#
# https://setuptools.readthedocs.io/en/latest/ (2018-09-04)
#

# PEP 345
# https://www.python.org/dev/peps/pep-0345/

# PEP 440 -- Version Identification and Dependency Specification
# https://www.python.org/dev/peps/pep-0440/


py_version = (sys.version_info.major, sys.version_info.minor)
install_requires = [
    # Syntax introduced sometime between setuptools-32.1.0 and setuptools-36.7.0
    # 'enum34>=1.1.6;python_version<"3.4"',
    # https://stackoverflow.com/questions/21082091/install-requires-based-on-python-version
    'mqtt-codec~=1.0',
]
if py_version < (3, 4):
    install_requires.append('enum34>=1.1.6')


project_dir = abspath(dirname(__file__))
chdir(project_dir)
setup(
    name="haka-mqtt",
    version="0.3.0",
    # Want to specify opt-in versions but found that when using
    # pip 9.0.3 (who knows what other versions), the comma seems to
    # prevent any part of the string from being recognized.
    #
    # python_requires='==2.7.*,==3.4.*,==3.5.*,==3.6.*,==3.7.*',
    #
    python_requires='>=2.7',
    install_requires=install_requires,
    tests_require=['mock'],
    use_2to3=True,
    packages=['haka_mqtt'],
    scripts=glob("scripts/*.py"),
    test_suite="tests",
    author="Keegan Callin",
    author_email="kc@kcallin.net",
    # license param is used when the license is not specified as a trove
    # classifier. According to note (5) at
    #
    #   Writing the Setup Script, Note 5, https://docs.python.org/3/distutils/setupscript.html#additional-meta-data
    #     Retrieved 2018-11-17.
    #
    url="https://github.com/kcallin/haka-mqtt",   # project home page
    description="Weapons grade MQTT client.",
    # Instruction on how to create a good README.rst
    #
    # https://packaging.python.org/guides/making-a-pypi-friendly-readme/
    #
    long_description=read_path('README.rst'),
    long_description_content_type='text/x-rst',
    project_urls={
        "Bug Tracker": "https://github.com/kcallin/haka-mqtt/issues",
        "Documentation": "https://haka-mqtt.readthedocs.io/en/latest/",
        "Source Code": "https://github.com/kcallin/haka-mqtt",
    },
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Communications',
        'Topic :: Internet',
        'Topic :: Software Development',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
        'Operating System :: POSIX :: Linux',
    ],
)

