#!/usr/bin/env bash
# Build USDA's BESTPRED as a reference for checking the port: tools/reference.sh OUTDIR
# Needs git, gcc and gfortran. Clones https://github.com/wintermind/bestpred into OUTDIR and builds two drivers there:
# OUTDIR/driver (Format 4 records -> every output, full precision) and OUTDIR/agedriver (a grid of age factors).
#
# Two build choices matter for an exact comparison:
#   - no bounds checking (as USDA's production build): with -fcheck=all the original stops on a plotting loop that
#     reads one element before an array when the last usable test day has no usable yield; the results don't use it.
#   - -ffp-contract=off: without it, compilers that fuse multiply-adds (clang and gcc on Apple silicon) can round an
#     SCS adjustment that lands exactly on .5 the other way. Off gives plain IEEE double arithmetic, as on x86.
set -euo pipefail
out="${1:?usage: tools/reference.sh OUTDIR}"
here="$(cd "$(dirname "$0")" && pwd)"
[ -d "$out/.git" ] || git clone --depth 1 https://github.com/wintermind/bestpred.git "$out"
cd "$out"
F="-O2 -ffp-contract=off -fno-underscoring -fno-automatic -ffree-line-length-none -w"
gcc -O2 -ffp-contract=off -I. -w -c ageadjs.c aiplage.c
gfortran $F -c bestpred_parm.f90 bestpred_log.f90
gfortran $F -c bestpred.f90
gfortran $F -c bestpred_fmt4.f90
gfortran $F "$here/driver.f90" bestpred_fmt4.o bestpred.o bestpred_parm.o bestpred_log.o aiplage.o ageadjs.o -o driver
gcc -O2 -ffp-contract=off -I. -w "$here/agedriver.c" aiplage.o ageadjs.o -o agedriver
echo "built $out/driver and $out/agedriver"
