from setuptools import setup, find_packages


setup(
    name = "gondor",
    version = "1.0a1.dev2",
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
    install_requires = [
        "argparse",
    ]
)
