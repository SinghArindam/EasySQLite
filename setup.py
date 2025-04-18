# setup.py
from setuptools import setup, find_packages

# Read README for long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="easy-sqlite-lib", # Choose a unique name for PyPI
    version="0.1.0",      # Sync with __init__.py
    author="Arindam Singh",   # Replace with your name
    author_email="aa7is789@gmail.com", # Replace with your email
    description="A user-friendly Python wrapper for SQLite.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/SinghArindam/EasySQLite", # Replace with your repo URL (optional)
    packages=find_packages(), # Automatically find the 'easysqlite' package
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: Apache Software License", # Choose your license
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Development Status :: 4 - Beta", # Or 5 - Production/Stable once ready
    ],
    python_requires='>=3.8', # Minimum Python version dependency
    install_requires=[
        # No external dependencies required based on the implementation
        # Add any if needed in the future, e.g., 'typing_extensions; python_version<"3.8"'
    ],
    keywords="sqlite sqlite3 database wrapper easy simple python",
    project_urls={ # Optional
        'Bug Reports': 'https://github.com/SinghArindam/EasySQLite/issues',
        'Source': 'https://github.com/SinghArindam/EasySQLite',
    },
)