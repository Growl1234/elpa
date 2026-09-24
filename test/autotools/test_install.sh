#!/bin/sh
# SPDX-License-Identifier: LGPL-3.0-only
# Run against a non-MPI installation selected by PKG_CONFIG_PATH.
# Static builds require explicit EXTRA_LIBS and, as needed, C_LINKER=the FC.
set -eu
srcdir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${CC:=cc}" "${FC:=gfortran}" "${PKG_CONFIG:=pkg-config}"
: "${C_LINKER:=$CC}" "${EXTRA_LIBS:=}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
cflags=$($PKG_CONFIG --cflags elpa)
libs=$($PKG_CONFIG --libs elpa)
libdir=$($PKG_CONFIG --variable=libdir elpa)
if $PKG_CONFIG --print-variables elpa | grep -qx fcflags; then
    echo 'Unexpected nonstandard fcflags in elpa.pc' >&2
    exit 1
fi
# Compiler commands and pkg-config output intentionally undergo shell splitting.
$CC ${CFLAGS:-} $cflags -std=c11 -c "$srcdir/installed_c.c" -o "$work/installed_c.o"
$C_LINKER "$work/installed_c.o" $libs $EXTRA_LIBS -lm -o "$work/installed_c"
$FC ${FCFLAGS:-} $cflags "$srcdir/installed_fortran.F90" $libs $EXTRA_LIBS -o "$work/installed_fortran"
export LD_LIBRARY_PATH="$libdir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
"$work/installed_c"
"$work/installed_fortran"
