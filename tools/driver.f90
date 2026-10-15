! Reference driver for the Python port: reads Format 4 records (one per line, ntd and segments included) from the
! file named on the command line, runs each through USDA's bestpred_fmt4() with the settings in bestpred.par, and
! prints every output at full precision. Build it with USDA's sources (see tools/reference.sh).
program driver
  implicit none
  real*8 :: DCRm, DCRc, DCRs, YLDvec(2,16), PERSvec(4), RELyld(4), RELpers(4), Yvec(2,4), herd305(2,4), bump(4)
  real*8 :: DAILYbp(4,999), DAILYherd(4,999)
  character(len=1400) :: format4
  character(len=100) :: BLUPout(10)
  character(len=256) :: infile
  integer :: BLUPn(10), ios, i
  integer*2 :: doprev
  integer :: GRAFplot(4), dim0(8), source, DEBUGmsgs, maxprnt, ONscreen, mtrait, use3X, GLOBALmtrait, obs, maxshow, &
             laclen, dailyfreq, maxlen, WRITEcurve, WRITEdata, plotfreq, maxtd, breed11, breedUNK, dim0flag, LOGon, &
             LOGfreq, CURVEsmall, CURVEsingle, region, season
  character :: INTmethod, INTmethodSCS, UNITSin, UNITSout
  real*8 :: PERSfloor, PERSceiling
  character(len=64) :: INfile64, OUTfile, CURVEfile, DATAfile, LOGfile

  call read_parms(laclen, maxlen, dailyfreq, plotfreq, use3X, mtrait, GLOBALmtrait, GRAFplot, PERSfloor, PERSceiling, &
                  source, WRITEcurve, CURVEfile, WRITEdata, DATAfile, INfile64, OUTfile, maxprnt, ONscreen, obs, &
                  maxshow, maxtd, INTmethod, INTmethodSCS, DEBUGmsgs, UNITSin, UNITSout, breed11, breedUNK, dim0, &
                  dim0flag, LOGon, LOGfile, LOGfreq, CURVEsmall, CURVEsingle, region, season)
  ! read_parms() resets the season curves (C, T for milk, fat and protein; D, U for SCS) to 'L', so USDA's
  ! command-line program never uses them; optional arguments 2 and 3 set the methods after it, as a caller can.
  if (command_argument_count() >= 3) then
    call get_command_argument(2, infile)
    INTmethod = infile(1:1)
    call get_command_argument(3, infile)
    INTmethodSCS = infile(1:1)
  end if
  call get_command_argument(1, infile)
  open(10, file=trim(infile))
  do
    read(10, '(a)', iostat=ios) format4
    if (ios /= 0) exit
    herd305 = 0.d0
    doprev = 0
    DAILYbp = 0.d0
    call bestpred_fmt4(format4, doprev, 0, DCRm, DCRc, DCRs, YLDvec, PERSvec, RELyld, RELpers, &
                       Yvec, herd305, bump, BLUPout, BLUPn, 0, GRAFplot, 0, 0, mtrait, use3X, laclen, dailyfreq, &
                       INTmethod, maxlen, DAILYbp, DAILYherd, 0, CURVEfile, 0, DATAfile, plotfreq, INTmethodSCS, 0, &
                       UNITSin, UNITSout, breedUNK, dim0, dim0flag, 0, LOGfile, 0, 0, CURVEsmall, CURVEsingle, &
                       region, season)
    write(*, '(a,999es25.16e3)') 'R ', DCRm, DCRc, DCRs, YLDvec(1,:), YLDvec(2,:), PERSvec, RELyld, RELpers, &
                                  Yvec(1,:), Yvec(2,:), herd305(1,:), bump
    ! bestpred() fills DAILYbp as (2, 4, maxlen); print it in that order.
    write(*, '(a,9999es25.16e3)') 'D ', (DAILYbp(mod(i-1,4)+1, (i-1)/4+1), i = 1, 8*maxlen)
  end do
end program driver
