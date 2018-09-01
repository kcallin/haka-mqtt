from setuptools import setup, find_packages

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
    project_urls={
        "Bug Tracker": "https://github.com/kcallin/haka-mqtt/issues",
#        "Documentation": "https://docs.example.com/HelloWorld/",
        "Source Code": "https://github.com/kcallin/haka-mqtt",
    }
)

