from setuptools import setup, find_packages


setup(
    name = "gondor",
    version = "1.0a1.dev5",
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
        "argparse",
        "argia",
        "redis==2.0.0",
    ]
)
