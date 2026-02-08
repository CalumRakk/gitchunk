from setuptools import find_packages, setup

from gitchunk import __version__

setup(
    name="gitchunk",
    version=__version__,
    author="Leo",
    author_email="leocasti2@gmail.com",
    url="https://github.com/CalumRakk/gitchunk",
    packages=find_packages(),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "gitchunk = gitchunk.cli:run_script",
        ],
    },
    include_package_data=True,
    install_requires=[
        "GitPython==3.1.45",
        "pydantic-settings==2.10.1",
        "packaging==26.0",
        "typer==0.21.1",
    ],
)
