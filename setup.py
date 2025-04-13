from setuptools import setup, find_packages
import codecs
import os

here = os.path.abspath(os.path.dirname(__file__))

with codecs.open(os.path.join(here, "README.md"), encoding="utf-8") as fh:
    long_description = "\n" + fh.read()

VERSION = '0.1.33'
DESCRIPTION = 'Python utility library.'
LONG_DESCRIPTION = 'A general purpose library for Python containing various utilities.'

# Setting up
setup(
    name="pylizlib",
    version=VERSION,
    author="Gabliz",
    author_email="",
    description=DESCRIPTION,
    long_description_content_type="text/markdown",
    long_description=long_description,
    packages=find_packages(),
    install_requires=[
        "requests",
        "GitPython",
        "rich"
    ],
    entry_points={
        "console_scripts": [
            "pyliz=pylizlib.cli:main",
        ],
    },
    keywords=['python', 'configuration', 'utilities'],
    classifiers=[
        "Development Status :: 1 - Planning",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Operating System :: Unix",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
    ]
)