from setuptools import setup, find_packages


setup(
    name="chatp",
    version="0.0.1",
    description="Utility tools in ChatApp",
    author="Roeder Lee",
    packages=find_packages("src"),
    include_package_data=True,
    package_dir={"": "src"},
    zip_safe=True,
)
