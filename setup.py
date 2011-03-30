import sys

from setuptools import setup, find_packages

from gondor import __version__


install_requires = []
if sys.version_info < (2, 7):
    install_requires.append("argparse==1.1")


setup(
    name = "gondor",
    version = __version__,
    description = "Eldarion infrastructure tools",
    author = "Eldarion",
    author_email = "development@eldarion.com",
    packages = find_packages(),
    package_data = {
        "gondor": [
            "ssl/*.crt",
        ]
    },
    zip_safe = False,
    entry_points = {
        "console_scripts": [
            "gondor = gondor.__main__:main",
        ],
    },
    dependency_links = [
        "http://dist.eldarion.com/gondor/argia/",
    ],
    install_requires = install_requires,
)
