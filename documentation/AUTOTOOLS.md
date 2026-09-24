# Autotools configuration and installation contract

## One installation, one configuration

**A single ELPA installation prefix must represent a single build configuration.**
The library is always `libelpa`, its pkg-config module is always `elpa`, and the
kernel-reporting executable is always `elpa2_print_kernels`. MPI, OpenMP and
accelerator settings are build properties, not separate public package names.

This is an intentional interface change, not a suffix option with a new default.
ELPA does not provide a suffix-compatibility mode. Multiple configurations remain
supported through independent build directories and installation prefixes. A
packager can instead supply a fully isolated dependency-stack hierarchy, but
changing `libdir` alone is insufficient: generated headers, Fortran modules,
pkg-config metadata and tools must not overwrite another configuration.

The default layout is:

```text
PREFIX/lib[64]/libelpa.so[.ABI]   # or libelpa.a
PREFIX/lib[64]/pkgconfig/elpa.pc
PREFIX/include/elpa/*.h
PREFIX/include/elpa/elpa.mod
PREFIX/include/elpa/elpa_api.mod
PREFIX/include/elpa/elpa_constants.mod
PREFIX/bin/elpa2_print_kernels
```

Standard `--prefix`, `--libdir`, `--includedir` and `--bindir` options are honored.
`--with-fmoddir=DIR` optionally relocates only the public Fortran modules; a
relative directory is interpreted relative to the installation prefix.

`elpa.pc` contains no private `fcflags` variable. Its default interface is:

```pkgconfig
Libs: -L${libdir} -lelpa
Cflags: -I${includedir} -I${includedir}/elpa
```

A relocated Fortran module directory is appended to `Cflags`. Both C includes
such as `#include <elpa/elpa.h>` and Fortran `use elpa` use the normal
`pkg-config --cflags elpa` interface. OpenMP flags are not imposed on consumers
that only call the shared library.

The plain pkg-config link interface describes the ELPA library, matching the
CMake build's current pkg-config policy. It deliberately does **not** reconstruct
the private dependency closure for static consumers. Static applications must
supply their math/MPI/OpenMP/compiler runtime dependencies explicitly, or use the
CMake build and its native exported targets. Applications that call ScaLAPACK or
BLAS themselves must declare those direct dependencies even with shared ELPA.

Old binaries referring to `libelpa_openmp` or `libelpa_onenode` need rebuilding.
An unchanged numerical API or libtool ABI version does not preserve those old
library filenames. Consumers must also stop querying `fcflags` and stop assuming
versioned include/module directories.

## Build examples

Regenerate a Git checkout once with `./autogen.sh`. A release distribution already
contains `configure`. Build outside the source tree:

```sh
mkdir build && cd build
../configure --prefix=/opt/elpa --without-mpi --with-blas=generic \
  --with-cpu-kernels=generic
make -j
make install
```

For a loaded MPI and MKL environment (with `MKLROOT` defined):

```sh
../configure --prefix=/opt/elpa-mpich --with-mpi --enable-openmp \
  --with-blas=mkl --with-scalapack=mkl --disable-avx512-kernels
```

No hand-written BLAS/ScaLAPACK `CFLAGS`, `FCFLAGS` or `LDFLAGS` are required.
Compiler/MPI selection and deployment-specific optimization/hardening flags are
still ordinary user inputs. Runtime library visibility remains the responsibility
of the installation environment, loader configuration or site-supplied rpaths;
finding a library at configure time does not configure the runtime loader.

For an open-source provider:

```sh
../configure --with-blas=openblas --with-scalapack=generic
../configure --with-blas=flexiblas --with-scalapack=generic
```

Set `PKG_CONFIG_PATH` to the metadata for the intended MPI/dependency stack when
it is not in the default search path. MPI-specific ScaLAPACK package names are
preferred when available; the other MPI implementation's name is never tried.

## Math-provider choices

| Option | Values | Default |
| --- | --- | --- |
| `--with-blas` | `auto`, `mkl`, `openblas`, `flexiblas`, `generic`, `custom` | `auto` |
| `--with-scalapack` | `auto`, `mkl`, `generic`, `custom` | `auto` |
| `--with-blas-interface` | `lp64`, `ilp64` | `lp64` |
| `--with-mkl-root` | Installation directory; otherwise `MKLROOT` | Environment hint |
| `--with-mkl-threading` | `sequential`, `openmp`, `gnu`, `intel`, `tbb` | `sequential` |
| `--with-mkl-link` | `dynamic`, `static` | `dynamic` |
| `--with-mkl-blacs` | `auto`, `intelmpi`, `mpich`, `openmpi` | `auto` |

`auto` considers MKL when an installation-root hint is supplied, followed by
FlexiBLAS, OpenBLAS and generic BLAS/LAPACK. Explicit provider choices do not
silently switch to another provider. Every accepted stack passes a Fortran link
probe including BLAS and LAPACK symbols; MPI builds also check ScaLAPACK/BLACS.
The probes do not execute programs or launch MPI ranks.

Discovery produces one ordered `ELPA_MATH_LIBS` closure and dependency-local
`ELPA_MATH_CFLAGS`. Global user flags are preserved. The same resolved closure is
used for library and test links; package metadata does not search for dependencies
again. Static pkg-config providers are queried with `--static` when building
static-only ELPA.

MKL interface and cluster libraries are selected coherently. GNU Fortran uses the
GNU MKL interface on Linux; Intel Fortran uses the Intel interface. MKL `openmp`
threading selects the GNU/Intel runtime from the compiler; incompatible explicit
runtime combinations fail. MKL threading is independent of ELPA OpenMP.

MKL BLACS selection uses compile checks against the active MPI headers, not the
name of an `mpiexec` found on PATH. Known conflicts are rejected. Unknown MPI
implementations require an explicit BLACS choice, including when cross-compiling.
On Linux the MPICH choice follows the existing CMake finder's Intel-MPI BLACS
mapping. A successful link is **not** proof that arbitrary MPI implementations
are ABI-compatible; the intended compiler/MPI stack still needs runtime testing.

`--with-mkl-link=static` selects actual MKL archives and preserves their rescan
order; it does not change whether ELPA itself is shared. For generic providers,
the library symbols alone cannot establish the integer ABI. Non-MKL ILP64 stacks
therefore require an explicit custom-library declaration rather than a guessed
LP64/ILP64 result.

For a custom stack:

```sh
../configure --with-blas=custom --with-scalapack=custom \
  BLAS_LIBS='-L/opt/math/lib -lblas' \
  LAPACK_LIBS='-L/opt/math/lib -llapack' \
  SCALAPACK_LIBS='-L/opt/mpi/lib -lscalapack'
```

`LAPACK_LIBS` can be empty when `BLAS_LIBS` already supplies LAPACK. Supply
`MATH_CFLAGS` only for custom dependency includes/defines. Explicit `*_LIBS`
variables imply `custom` for an `auto` request; combining them with a different
explicit provider is an error. Legacy split BLACS installations remain possible
through `SCALAPACK_LIBS`, without maintaining a matrix of historical library-name
probes in ELPA itself.

`SCALAPACK_LDFLAGS` and `SCALAPACK_FCFLAGS` are removed. The old
`--enable-64bit-integer-math-support` option is replaced by
`--with-blas-interface=ilp64`. Site/CI configuration strings must migrate too.

## CPU kernels

Use the canonical `--enable/disable-<family>-kernels` options. The old unsuffixed
aliases are rejected with a migration diagnostic. `--with-cpu-kernels=generic`
selects only generic CPU kernels; it does not implicitly select or change an
accelerator backend.

On x86-64 the existing SSE/AVX/AVX2/AVX512 family defaults are retained. Other
target architectures do not enable x86 families by default. Intrinsic probes and
kernel compilation use family-specific options; these options are never applied
to the generic library objects. The build-host CPUID/OS-probing macro and its
unused helpers have been removed.

The configuration summary reports **compiled kernel families**, not instructions
available on all runtime nodes. The existing default/fixed-kernel selection and
runtime dispatch policy is not redesigned here. Select only appropriate families
and defaults for the deployment, or use a generic-only build. Invalid or disabled
default-kernel choices now fail at configure time.

## Regression tests

```sh
./autogen.sh
python3 test/autotools/test_math.py
```

The math-discovery tests use synthetic MKL libraries and MPI headers to cover
LP64/ILP64, shared/static MKL, GNU threading, MPI selection/conflicts, unknown MPI,
custom stacks, invalid input and preservation of global flags. They are configure
and link-assembly tests, **not** validation of a real MKL installation, Intel
compiler or MPI runtime. They can also be invoked with `make check-build-system`.

After installing a non-MPI shared build:

```sh
PKG_CONFIG_PATH=/path/to/elpa/lib/pkgconfig test/autotools/test_install.sh
```

This compiles independent C and Fortran consumers using the installed metadata
and checks both eigensolvers against a dense orthogonal transform of an analytic
tridiagonal problem, including
residuals and eigenvector orthogonality. For a static GNU/OpenMP build with generic
BLAS/LAPACK:

```sh
PKG_CONFIG_PATH=/path/to/elpa-static/lib/pkgconfig \
  C_LINKER=gfortran EXTRA_LIBS='-fopenmp -llapack -lblas' \
  test/autotools/test_install.sh
```

Real MKL, multiple MPI implementations and accelerator configurations require the
corresponding site environments. This refactor does not claim to validate those
runtime combinations through simulated link fixtures.
