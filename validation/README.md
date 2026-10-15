# Validation

Best prediction projections checked against daily meter weights.

## Data

`data/synthetic_daily.csv.gz`: 600 synthetic Holstein lactations, one row per cow-day, 305 days, about 12% of days
missing. No real cows. Drawn from herd-level summaries of a California herd (`data/synthetic_params.json`): parity
mix, average curve by parity, cow-to-cow spread in level and persistency, day-to-day variation, share of days not
weighed.

## Method

- True yield: sum of daily weights to 305 days, missing days interpolated.
- Test days: monthly from the daily weights, first test 5 to 35 DIM, then every 30 ± 4 days.
- 305-day yield projected from tests up to 60, 120 and 200 DIM, and from all tests.
- Compared with two simple projections: the cow's tests as a ratio to the herd curve, and test intervals plus the
  herd curve after the last test.
- Five draws of test days.

## Results

Mean absolute error, % of 305-day yield. 490 lactations (those with 85% of days weighed and no gap over 7 days).

| Tests to | Best prediction | Herd-curve ratio | Test intervals + herd curve |
|---|---|---|---|
| 60 DIM | 7.9 | 8.5 | 8.3 |
| 120 DIM | 5.4 | 6.0 | 5.5 |
| 200 DIM | 3.0 | 3.6 | 3.0 |
| All tests | 1.8 | 2.0 | 1.8 |

Full table: `results/summary_305d.csv`.

## Run it

```bash
git clone https://github.com/padge01/bestpred-python && cd bestpred-python
pip install -e ".[validation]"
python validation/herd_test.py validation/data/synthetic_daily.csv.gz --end 305 --seed 1
```

`herd_test.py` takes any CSV of daily weights with columns cow, parity, breed, birth_date, fresh_date, dim, milk.
`make_synthetic.py fit` summarises a herd's daily weights; `make_synthetic.py make` draws synthetic lactations from
the summary.
