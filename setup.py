from setuptools import setup, find_packages

from gondor import __version__


setup(
    name="gondor",
    version=__version__,
    description="official gondor.io command line client",
    url="https://github.com/eldarion/gondor-client",
    author="Eldarion",
    author_email="development@eldarion.com",
    packages=find_packages(),
    package_data={
        "gondor": [
            "ssl/*.crt",
            "yaml-py2-3.10.zip",
            "yaml-py3-3.10.zip",
        ]
    },
    zip_safe=False,
    entry_points={
        "console_scripts": [
            "gondor = gondor.__main__:main",
        ],
    },
    install_requires=[
        "six>=1.3.0",
    ],
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
)
