import os

from setuptools import setup, Extension
from Cython.Build import cythonize


if os.name == "nt":
    compile_args = ["/std:c++17", "/O2"]
else:
    compile_args = ["/std:c++17", "-O3"]


extensions = [
    Extension(
        name="Ncore.tl",
        sources=["src/Ncore/tl.pyx"],
        extra_compile_args=compile_args,
        language="c++",
    )
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
            "nonecheck": False,
            "initializedcheck": False,
        }
    ),
)
