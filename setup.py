import sys

from setuptools import setup, find_packages

from gondor import __version__


install_requires = []
if sys.version_info < (2, 7):
    install_requires.append("argparse==1.1")


setup(
    name = "gondor",
    version = __version__,
    description = "official gondor.io command line client",
    url = "https://github.com/eldarion/gondor-client",
    author = "Eldarion",
    author_email = "development@eldarion.com",
    packages = find_packages(),
    package_data = {
        "gondor": [
            "ssl/*.crt",
            "yaml-3.10.zip",
        ]
    },
    zip_safe = False,
    entry_points = {
        "console_scripts": [
            "gondor = gondor.__main__:main",
        ],
    },
    install_requires = install_requires,
)
