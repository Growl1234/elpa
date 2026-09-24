/* SPDX-License-Identifier: LGPL-3.0-only */
/* Exercise the installed C API, including both eigensolvers and real kernels. */
#include <elpa/elpa.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static void check(int error, const char *operation) {
    if (error != ELPA_OK) {
        fprintf(stderr, "%s failed: %d\n", operation, error);
        exit(EXIT_FAILURE);
    }
}

int main(void) {
    enum { n = 32 };
    int error;
    check(elpa_init(20260202), "elpa_init");
    for (int solver = ELPA_SOLVER_1STAGE; solver <= ELPA_SOLVER_2STAGE; ++solver) {
        double a[n * n], original[n * n], q[n * n] = {0}, ev[n], v[n], tv[n];
        elpa_t handle = elpa_allocate(&error);
        check(error, "elpa_allocate");
        elpa_set(handle, "na", n, &error); check(error, "na");
        elpa_set(handle, "nev", n, &error); check(error, "nev");
        elpa_set(handle, "local_nrows", n, &error); check(error, "local_nrows");
        elpa_set(handle, "local_ncols", n, &error); check(error, "local_ncols");
        elpa_set(handle, "nblk", 4, &error); check(error, "nblk");
        elpa_set(handle, "solver", solver, &error); check(error, "solver");
        check(elpa_setup(handle), "elpa_setup");
        double norm = sqrt(n * (n + 1.0) * (2 * n + 1.0) / 6.0);
        for (int i = 0; i < n; ++i) v[i] = (i + 1) / norm;
        double vtv = 0.0;
        for (int i = 0; i < n; ++i) {
            tv[i] = 2.0 * v[i];
            if (i > 0) tv[i] -= v[i - 1];
            if (i + 1 < n) tv[i] -= v[i + 1];
            vtv += v[i] * tv[i];
        }
        for (int j = 0; j < n; ++j) {
            for (int i = 0; i < n; ++i) {
                double tij = i == j ? 2.0 : (abs(i - j) == 1 ? -1.0 : 0.0);
                original[i + j * n] = tij - 2.0 * (v[i] * tv[j] + tv[i] * v[j])
                                         + 4.0 * vtv * v[i] * v[j];
                a[i + j * n] = original[i + j * n];
            }
        }
        elpa_eigenvectors(handle, a, ev, q, &error);
        check(error, "elpa_eigenvectors");
        double residual = 0.0, orthogonality = 0.0, eigenvalue_error = 0.0;
        for (int j = 0; j < n; ++j) {
            double exact = 2.0 - 2.0 * cos((j + 1) * acos(-1.0) / (n + 1));
            eigenvalue_error = fmax(eigenvalue_error, fabs(ev[j] - exact));
            for (int i = 0; i < n; ++i) {
                double r = -ev[j] * q[i + j * n];
                for (int k = 0; k < n; ++k) r += original[i + k * n] * q[k + j * n];
                residual = fmax(residual, fabs(r));
                double dot = 0.0;
                for (int k = 0; k < n; ++k) dot += q[k + i * n] * q[k + j * n];
                orthogonality = fmax(orthogonality, fabs(dot - (i == j ? 1.0 : 0.0)));
            }
        }
        printf("C solver %d: eigenvalues %.3e, residual %.3e, orthogonality %.3e\n",
               solver, eigenvalue_error, residual, orthogonality);
        if (fmax(eigenvalue_error, fmax(residual, orthogonality)) > 1.e-11) return EXIT_FAILURE;
        elpa_deallocate(handle, &error); check(error, "elpa_deallocate");
    }
    elpa_uninit(&error); check(error, "elpa_uninit");
    return EXIT_SUCCESS;
}
