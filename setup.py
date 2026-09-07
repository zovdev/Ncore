import sys
from pathlib import Path

from setuptools import setup, Extension
from Cython.Build import cythonize


if sys.platform == "win32":
    c_args = ["/O2"]
    cpp_args = ["/std:c++17", "/O2"]
else:
    c_args = ["-std=c11", "-O3"]
    cpp_args = ["-std=c++17", "-O3"]

module_path = Path("src/Ncore/modules/")

extensions = [
    Extension(
        name="Ncore.tl",
        sources=[str(module_path / "tl" / "tl.pyx")],
        include_dirs=[str(module_path / "tl")],
        extra_compile_args=cpp_args,
        language="c++"
    ),
    Extension(
        name="Ncore.ncrypto",
        sources=[str(module_path / "ncrypto" / "ncrypto.pyx"), str(module_path / "ncrypto" / "ncrypto_aes.c")],
        extra_compile_args=c_args,
    )
]

setup(ext_modules=cythonize(extensions))
