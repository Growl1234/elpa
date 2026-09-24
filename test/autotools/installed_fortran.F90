! SPDX-License-Identifier: LGPL-3.0-only
! Compile using only pkg-config --cflags elpa (no private fcflags variable).
program installed_fortran
  use iso_c_binding, only: c_double
  use elpa
  implicit none
  integer, parameter :: n = 32
  integer :: i, j, solver, error
  real(c_double) :: a(n,n), q(n,n), ev(n), work(n,n), identity(n,n), exact(n)
  real(c_double) :: residual, orthogonality, eigenvalue_error, v(n), tv(n), vtv
  class(elpa_t), pointer :: handle

  call check(elpa_init(20260202))
  do solver = ELPA_SOLVER_1STAGE, ELPA_SOLVER_2STAGE
    handle => elpa_allocate(error)
    call check(error)
    call handle%set('na', n, error); call check(error)
    call handle%set('nev', n, error); call check(error)
    call handle%set('local_nrows', n, error); call check(error)
    call handle%set('local_ncols', n, error); call check(error)
    call handle%set('nblk', 4, error); call check(error)
    call handle%set('solver', solver, error); call check(error)
    call check(handle%setup())
    a = 0.0_c_double
    identity = 0.0_c_double
    do i = 1, n
      a(i,i) = 2.0_c_double
      identity(i,i) = 1.0_c_double
      exact(i) = 2.0_c_double - 2.0_c_double*cos(i*acos(-1.0_c_double)/(n+1))
      if (i < n) then
        a(i,i+1) = -1.0_c_double
        a(i+1,i) = -1.0_c_double
      end if
    end do
    ! Orthogonal similarity transform of the tridiagonal matrix: dense H*T*H.
    v = [(real(i, c_double), i=1,n)]
    v = v/sqrt(dot_product(v,v))
    tv = matmul(a,v)
    vtv = dot_product(v,tv)
    do j = 1, n
      do i = 1, n
        a(i,j) = a(i,j) - 2.0_c_double*(v(i)*tv(j) + tv(i)*v(j)) &
                        + 4.0_c_double*vtv*v(i)*v(j)
      end do
    end do
    work = a
    call handle%eigenvectors(a, ev, q, error)
    call check(error)
    a = matmul(work, q)
    do j = 1, n
      a(:,j) = a(:,j) - ev(j)*q(:,j)
    end do
    residual = maxval(abs(a))
    orthogonality = maxval(abs(matmul(transpose(q),q)-identity))
    eigenvalue_error = maxval(abs(ev-exact))
    print '(a,i1,a,3es12.3)', 'Fortran solver ', solver, ': ', eigenvalue_error, residual, orthogonality
    if (max(eigenvalue_error, residual, orthogonality) > 1.e-11_c_double) stop 1
    call elpa_deallocate(handle, error)
    call check(error)
  end do
  call elpa_uninit(error)
  call check(error)
contains
  subroutine check(code)
    integer, intent(in) :: code
    if (code /= ELPA_OK) then
      print *, 'ELPA operation failed: ', code
      stop 1
    end if
  end subroutine
end program
