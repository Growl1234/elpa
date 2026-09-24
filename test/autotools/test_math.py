#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-only
"""Link-discovery regression tests; synthetic MKL/MPI fixtures are NOT runtime tests.

Run from any directory with Python 3, Autoconf, a C/Fortran compiler, ar and
pkg-config installed. Everything is generated in a temporary directory.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]


def run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=120, check=False)


@unittest.skipUnless(sys.platform.startswith("linux"), "Synthetic MKL/BLACS fixtures model Linux")
class MathDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for tool in ("autoconf", "cc", "gfortran", "ar", "pkg-config"):
            if shutil.which(tool) is None:
                raise unittest.SkipTest(f"{tool} is required")
        cls.temp = tempfile.TemporaryDirectory(prefix="elpa-math-tests-")
        cls.base = Path(cls.temp.name)
        cls.project = cls.base / "project"
        cls.project.mkdir()
        for name in ("config.guess", "config.sub"):
            candidates = [SOURCE / name, Path("/usr/share/misc") / name,
                          Path("/usr/share/automake-1.17") / name,
                          Path("/usr/share/automake-1.16") / name]
            src = next((p for p in candidates if p.is_file()), None)
            if src is None:
                raise unittest.SkipTest(f"Generate {name} with autoreconf first")
            shutil.copy(src, cls.project / name)
        includes = "\n".join(f"m4_include([{SOURCE / 'm4' / name}])" for name in
                             ("ax_fc_check_define.m4", "elpa_math.m4", "elpa_mkl.m4"))
        (cls.project / "configure.ac").write_text(includes + """
AC_INIT([elpa-math-test], [1])
AC_CONFIG_SRCDIR([configure.ac])
AC_CANONICAL_HOST
ELPA_MATH_OPTIONS
AC_PROG_CC
AC_PROG_FC([gfortran])
AC_FC_SRCEXT([F90])
AC_ARG_WITH([mpi], [], [], [with_mpi=no])
AC_ARG_ENABLE([shared], [], [], [enable_shared=yes])
ELPA_FIND_MATH
AC_CONFIG_FILES([state])
AC_OUTPUT
""")
        (cls.project / "state.in").write_text("""blas=@ELPA_BLAS_PROVIDER@
scalapack=@ELPA_SCALAPACK_PROVIDER@
mpi=@ELPA_MPI_VENDOR@
math_libs=@ELPA_MATH_LIBS@
math_cflags=@ELPA_MATH_CFLAGS@
CFLAGS=@CFLAGS@
CPPFLAGS=@CPPFLAGS@
FCFLAGS=@FCFLAGS@
LDFLAGS=@LDFLAGS@
LIBS=@LIBS@
""")
        result = run(["autoconf"], cls.project)
        if result.returncode:
            raise RuntimeError(result.stdout)
        cls.mkl = cls.base / "mkl"
        (cls.mkl / "lib").mkdir(parents=True)
        (cls.mkl / "include").mkdir()
        cls.pcdir = cls.base / "pkgconfig"
        cls.pcdir.mkdir()
        for abi in ("lp64", "ilp64"):
            cls.library(f"mkl_gf_{abi}", "void dgemm_(void) {}\nvoid dsyev_(void) {}\nvoid dlarrv_(void) {}")
            cls.library(f"mkl_scalapack_{abi}", "void blacs_gridinit_(void);\nvoid pdtran_(void) { blacs_gridinit_(); }")
            for mpi in ("intelmpi", "openmpi"):
                cls.library(f"mkl_blacs_{mpi}_{abi}", "void blacs_gridinit_(void) {}")
        for layer in ("core", "sequential", "gnu_thread", "intel_thread", "tbb_thread"):
            cls.library(f"mkl_{layer}", f"void stub_{layer}(void) {{}}")
        cls.library("openblas", "void dgemm_(void) {}\nvoid dsyev_(void) {}\nvoid dlarrv_(void) {}")
        cls.library("pc_private", "void private_dependency(void) {}")
        cls.library("pc_blas", "void private_dependency(void);\nvoid dgemm_(void) {private_dependency();}\nvoid dsyev_(void) {}\nvoid dlarrv_(void) {}")
        cls.headers = {}
        for mpi, define in (("mpich", '#define MPICH_VERSION "test"'),
                            ("openmpi", "#define OMPI_MAJOR_VERSION 5"),
                            ("intelmpi", "#define I_MPI_VERSION 20210000"),
                            ("unknown", "/* unknown implementation */")):
            directory = cls.base / mpi
            directory.mkdir()
            (directory / "mpi.h").write_text(define + "\n")
            cls.headers[mpi] = directory

    @classmethod
    def library(cls, name: str, code: str) -> None:
        src = cls.base / f"{name}.c"
        obj = cls.base / f"{name}.o"
        src.write_text(code + "\n")
        for command in (["cc", "-fPIC", "-c", str(src), "-o", str(obj)],
                        ["cc", "-shared", str(obj), "-o", str(cls.mkl / "lib" / f"lib{name}.so")],
                        ["ar", "rcs", str(cls.mkl / "lib" / f"lib{name}.a"), str(obj)]):
            result = run(command, cls.base)
            if result.returncode:
                raise RuntimeError(result.stdout)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def configure(self, *options: str, mpi: str | None = None,
                  variables: dict[str, str] | None = None,
                  error: str | None = None) -> dict[str, str]:
        build = Path(tempfile.mkdtemp(prefix="build-", dir=self.base))
        env = os.environ.copy()
        for key in ("CC", "FC", "F77", "CFLAGS", "CPPFLAGS", "FCFLAGS", "FFLAGS",
                    "LDFLAGS", "LIBS", "BLAS_LIBS", "LAPACK_LIBS", "SCALAPACK_LIBS",
                    "SCALAPACK_LDFLAGS", "SCALAPACK_FCFLAGS", "MATH_CFLAGS", "MKLROOT",
                    "CONFIG_SITE", "PKG_CONFIG", "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR"):
            env.pop(key, None)
        env.update(CC="cc", FC="gfortran", CONFIG_SITE="/dev/null",
                   PKG_CONFIG_LIBDIR=str(self.pcdir))
        if mpi:
            env["CPPFLAGS"] = f"-I{self.headers[mpi]}"
        if variables:
            env.update(variables)
        result = run([str(self.project / "configure"), *options], build, env)
        if error is not None:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(error, result.stdout)
            return {}
        self.assertEqual(result.returncode, 0, result.stdout)
        return dict(line.split("=", 1) for line in (build / "state").read_text().splitlines())

    def mkl_options(self) -> list[str]:
        return ["--with-blas=mkl", f"--with-mkl-root={self.mkl}"]

    def metadata(self, name: str, libs: str, private: str = "", cflags: str = "") -> Path:
        directory = Path(tempfile.mkdtemp(prefix="pc-", dir=self.base))
        (directory / f"{name}.pc").write_text(
            f"Name: {name}\nDescription: synthetic discovery fixture\nVersion: 1\n"
            f"Libs: {libs}\nLibs.private: {private}\nCflags: {cflags}\n")
        return directory

    def test_openblas_pkgconfig(self) -> None:
        directory = self.metadata("openblas", f"-L{self.mkl / 'lib'} -lopenblas",
                                  cflags="-DMATH_METADATA=1")
        state = self.configure("--with-blas=openblas", variables={"PKG_CONFIG_LIBDIR": str(directory)})
        self.assertEqual(state["blas"], "openblas")
        self.assertIn("-DMATH_METADATA=1", state["math_cflags"])
        self.assertNotIn("MATH_METADATA", state["CPPFLAGS"])

    def test_static_pkgconfig_private_closure(self) -> None:
        directory = self.metadata("openblas", str(self.mkl / "lib/libpc_blas.a"),
                                  private=str(self.mkl / "lib/libpc_private.a"))
        state = self.configure("--with-blas=openblas", "--disable-shared",
                               variables={"PKG_CONFIG_LIBDIR": str(directory)})
        self.assertIn("libpc_private.a", state["math_libs"])
        self.assertLess(state["math_libs"].index("libpc_blas.a"),
                        state["math_libs"].index("libpc_private.a"))

    def test_no_pkgconfig_fallback(self) -> None:
        state = self.configure("--with-blas=openblas",
                               variables={"PKG_CONFIG": "false", "LDFLAGS": f"-L{self.mkl / 'lib'}"})
        self.assertEqual(state["blas"], "openblas")
        self.assertIn("-lopenblas", state["math_libs"])

    def test_mpi_specific_scalapack_pkgconfig(self) -> None:
        directory = self.metadata("scalapack-mpich", f"-L{self.mkl / 'lib'} -lmkl_scalapack_lp64 -lmkl_blacs_intelmpi_lp64")
        state = self.configure("--with-mpi", "--with-scalapack=generic", mpi="mpich",
                               variables={"PKG_CONFIG_LIBDIR": str(directory),
                                          "BLAS_LIBS": f"-L{self.mkl / 'lib'} -lmkl_gf_lp64"})
        self.assertEqual(state["scalapack"], "scalapack-mpich")

    def test_missing_explicit_mkl_does_not_fallback(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="empty-mkl-", dir=self.base))
        self.configure("--with-blas=mkl", f"--with-mkl-root={directory}",
                       error="Requested MKL stack does not link")

    def test_scalapack_without_mpi_is_rejected(self) -> None:
        self.configure(*self.mkl_options(), "--with-scalapack=mkl",
                       error="--with-scalapack requires --with-mpi=yes")

    def test_mkl_lp64_dynamic(self) -> None:
        state = self.configure(*self.mkl_options())
        self.assertEqual(state["blas"], "mkl")
        self.assertEqual(state["scalapack"], "none")
        self.assertIn("-lmkl_gf_lp64", state["math_libs"])
        self.assertNotIn("-lmkl_intel_lp64", state["math_libs"])

    def test_mkl_ilp64_static_cluster(self) -> None:
        state = self.configure(*self.mkl_options(), "--with-mpi", "--with-scalapack=mkl",
                               "--with-blas-interface=ilp64", "--with-mkl-link=static", mpi="mpich")
        libs = state["math_libs"]
        self.assertEqual(state["mpi"], "mpich")
        self.assertIn("libmkl_blacs_intelmpi_ilp64.a", libs)
        self.assertIn("libmkl_gf_ilp64.a", libs)
        self.assertEqual(libs.count("--start-group"), 1)
        self.assertEqual(libs.count("--end-group"), 1)
        self.assertNotIn(".so", libs)

    def test_mkl_openmpi(self) -> None:
        state = self.configure(*self.mkl_options(), "--with-mpi", "--with-scalapack=mkl", mpi="openmpi")
        self.assertIn("-lmkl_blacs_openmpi_lp64", state["math_libs"])
        self.assertNotIn("-lmkl_blacs_intelmpi_lp64", state["math_libs"])

    def test_mkl_intelmpi(self) -> None:
        state = self.configure(*self.mkl_options(), "--with-mpi", "--with-scalapack=mkl", mpi="intelmpi")
        self.assertEqual(state["mpi"], "intelmpi")
        self.assertIn("-lmkl_blacs_intelmpi_lp64", state["math_libs"])

    def test_mkl_gnu_threading(self) -> None:
        state = self.configure(*self.mkl_options(), "--with-mkl-threading=openmp")
        self.assertIn("-lmkl_gnu_thread", state["math_libs"])
        self.assertIn("-lgomp", state["math_libs"])

    def test_mkl_auto_hint(self) -> None:
        state = self.configure(variables={"MKLROOT": str(self.mkl)})
        self.assertEqual(state["blas"], "mkl")

    def test_global_flags_preserved(self) -> None:
        values = dict(CFLAGS="-O1 -g", CPPFLAGS="-DUSER_DEFINE=1", FCFLAGS="-O1 -g",
                      LDFLAGS="-Wl,--as-needed", LIBS="-lm")
        state = self.configure(*self.mkl_options(), variables=values)
        for name, value in values.items():
            self.assertEqual(state[name], value, name)

    def test_custom_stack(self) -> None:
        state = self.configure(variables={"BLAS_LIBS": f"-L{self.mkl / 'lib'} -lmkl_gf_lp64"})
        self.assertEqual(state["blas"], "custom")

    def test_broken_custom_stack(self) -> None:
        self.configure("--with-blas=custom", variables={"BLAS_LIBS": "-lelpa_nonexistent_math"},
                       error="Custom BLAS/LAPACK do not link")

    def test_conflicting_mpi_abi(self) -> None:
        self.configure(*self.mkl_options(), "--with-mpi", "--with-scalapack=mkl",
                       "--with-mkl-blacs=openmpi", mpi="mpich", error="conflicts with MPI")

    def test_unknown_mpi_requires_choice(self) -> None:
        self.configure(*self.mkl_options(), "--with-mpi", "--with-scalapack=mkl",
                       mpi="unknown", error="Cannot determine MKL BLACS ABI")

    def test_unknown_mpi_explicit_choice(self) -> None:
        state = self.configure(*self.mkl_options(), "--with-mpi", "--with-scalapack=mkl",
                               "--with-mkl-blacs=mpich", mpi="unknown")
        self.assertEqual(state["scalapack"], "mkl")

    def test_no_guessing_ilp64(self) -> None:
        self.configure("--with-blas=generic", "--with-blas-interface=ilp64",
                       error="Automatic ILP64 discovery requires MKL")

    def test_provider_conflict(self) -> None:
        self.configure("--with-blas=mkl", variables={"BLAS_LIBS": "-lblas"},
                       error="cannot be combined")

    def test_invalid_choice(self) -> None:
        self.configure("--with-blas=typo", error="Invalid --with-blas")

    def test_removed_global_dependency_flags(self) -> None:
        self.configure(variables={"SCALAPACK_LDFLAGS": "-llapack -lblas"},
                       error="SCALAPACK_LDFLAGS/SCALAPACK_FCFLAGS were removed")

    def test_no_intel_openmp_with_gfortran(self) -> None:
        self.configure(*self.mkl_options(), "--with-mkl-threading=intel",
                       error="MKL Intel threading requires an Intel Fortran compiler")


if __name__ == "__main__":
    unittest.main(verbosity=2)
