from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="cacheref",
    version="0.1.0",
    author="",
    author_email="",
    description="A caching decorator that tracks entity references for precise invalidation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.7",
    install_requires=[],  # No mandatory dependencies
    extras_require={
        # Optional Redis support
        "redis": ["redis>=4.0.0"],
        # Optional ValKey support
        "valkey": ["valkey>=0.1.0"],
        # All backends
        "all": ["redis>=4.0.0", "valkey>=0.1.0"],
        # Development dependencies
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.0.0",
            "mypy>=1.0.0"
        ],
    },
)
