"""The Python API on its own terms: sensible answers, input handling, helpers."""

import numpy as np
import pytest

from bestpred import Settings, TestDay, bestpred, pday
from bestpred.format4 import ffmt, fnum


def monthly_tests(milk=80.0, n=10, start=15):
    return [TestDay(dim=start + 30 * k, milk=milk - 1.5 * k, fat=3.8, protein=3.1, scs=2.5) for k in range(n)]


def test_complete_lactation_is_close_to_the_sum_of_tests():
    res = bestpred(monthly_tests(), herdavg=(24000, 900, 750, 3.0), agefac=(1, 1, 1, 1), cowid='H', parity=2)
    milk305 = res.yields('actual')['milk']['305']
    assert 0.9 * 22000 < milk305 < 1.1 * 25000
    assert res.rel_yield[0] > 0.9
    assert 90 < res.dcr_milk < 110


def test_more_tests_raise_reliability():
    few = bestpred(monthly_tests(n=2), herdavg=(24000, 900, 750, 3.0), agefac=(1, 1, 1, 1), parity=2)
    many = bestpred(monthly_tests(n=10), herdavg=(24000, 900, 750, 3.0), agefac=(1, 1, 1, 1), parity=2)
    assert few.rel_yield[0] < many.rel_yield[0]


def test_no_tests_gives_the_herd_mean():
    res = bestpred([], herdavg=(24000, 900, 750, 3.0), agefac=(1, 1, 1, 1), fresh='20240101', parity=2)
    assert res.yldvec[0, 0] == pytest.approx(24000, rel=1e-6)
    assert res.rel_yield[0] == 0


def test_kilograms_in_and_out():
    lb = bestpred(monthly_tests(), herdavg=(24000, 900, 750, 3.0), agefac=(1, 1, 1, 1), parity=2)
    kg_tests = [TestDay(dim=t.dim, milk=t.milk / 2.205, fat=t.fat, protein=t.protein, scs=t.scs)
                for t in monthly_tests()]
    kg = bestpred(kg_tests, herdavg=(24000 / 2.205, 900 / 2.205, 750 / 2.205, 3.0), agefac=(1, 1, 1, 1), parity=2,
                  settings=Settings(units_in='K', units_out='K'))
    assert kg.yldvec[1, 0] * 2.205 == pytest.approx(lb.yldvec[1, 0], rel=1e-4)


def test_settings_are_checked():
    with pytest.raises(ValueError):
        Settings(mtrait=2)
    with pytest.raises(ValueError):
        Settings(laclen=400, maxlen=365)


def test_pday():
    assert pday('19600101') == 0
    assert pday('19600102') == 1
    assert pday('19610101') == 366
    assert pday('19591231') == -1
    assert pday('20000301') - pday('20000228') == 2


def test_fortran_number_fields():
    assert fnum('0670', 1) == 67.0
    assert fnum(' 38', 1) == 3.8
    assert fnum('    ') == 0.
    assert fnum('-120') == -120.


def test_fortran_output_fields():
    assert ffmt(22193.4, 7, 0) == ' 22193.'
    assert ffmt(2.5, 4, 0) == '  3.'
    assert ffmt(-0.001, 6, 2) == ' -0.00'
    assert ffmt(float('nan'), 7, 0) == '    NaN'
    assert ffmt(123456789., 5, 0) == '*****'


def test_daily_curves_have_the_herd_curve_and_the_cow():
    res = bestpred(monthly_tests(), herdavg=(24000, 900, 750, 3.0), agefac=(1, 1, 1, 1), parity=2)
    herd = res.daily_herd[1, 0, 1:306]
    cow = herd + res.daily_bp[1, 0, 1:306]
    assert np.isclose(herd.sum(), res.herd305[1, 0], rtol=1e-6)
    assert cow.max() > 60
