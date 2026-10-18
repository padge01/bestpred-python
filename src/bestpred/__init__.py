"""bestpred: USDA's best prediction of lactation yields and persistency (BESTPRED 2.0rc7), in Python.

A port of the public-domain Fortran and C programs by Paul VanRaden and John Cole (USDA-ARS Animal Genomics and
Improvement Laboratory), checked against the original. Not affiliated with or endorsed by USDA.
"""

from .adjust import adjscs, age_factors, aiplage, pday
from .core import Result, Settings, TestDay, bestpred
from .format4 import Format4, results_line, run_format4

__all__ = ['Format4', 'Result', 'Settings', 'TestDay', 'adjscs', 'age_factors', 'aiplage', 'bestpred', 'pday',
           'results_line', 'run_format4']
__version__ = '0.2.1'
