from setuptools import setup, find_packages

try:
    with open("README.md", "r", encoding="utf-8") as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = "Descripción del paquete"

setup(
    name="gitchunk",
    version="0.1.0",
    author="Leo",
    author_email="leocasti2@gmail.com",
    description="Script para hacer backup de archivos pequeños en un repositorio de github",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/CalumRakk/gitchunk",
    packages=find_packages(),
    py_modules=["gitchunk"],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gitchunk = gitchunk.cli:main",
        ],
    },
    include_package_data=True,
)
