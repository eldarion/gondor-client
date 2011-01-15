from setuptools import setup, find_packages

from gondor import __version__


setup(
    name = "gondor",
    version = __version__,
    description = "Eldarion infrastructure tools",
    author = "Eldarion",
    author_email = "development@eldarion.com",
    packages = find_packages(),
    zip_safe = False,
    entry_points = {
        "console_scripts": [
            "gondor = gondor.__main__:main",
        ],
    },
    dependency_links = [
        "http://dist.eldarion.com/gondor/argia/",
    ],
    install_requires = [
        "argparse==1.1",
    ]
)
