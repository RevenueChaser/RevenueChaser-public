from setuptools import setup, find_packages

packages = ["revenuechaser"] + ["revenuechaser." + p for p in find_packages(where=".")]

setup(
    name="revenuechaser",
    version="0.1.0",
    description="Event-driven earnings decision engine",
    packages=packages,
    package_dir={"revenuechaser": "."},
    python_requires=">=3.11",
)
