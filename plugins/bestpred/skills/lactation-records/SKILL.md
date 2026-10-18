---
name: lactation-records
description: Work out dairy cows' lactation records (305-day and mature-equivalent milk, fat and protein, reliability, persistency) from test days with USDA's best prediction method, using the bestpred tools. Use when someone asks for 305-day yields, mature equivalent, persistency, or a cow's expected milk from DHI or DairyComp test days.
---

# Lactation records with best prediction

Never work out a lactation record yourself. Call the bestpred tools and report what they return, as they return it.

## Which tool

- A herd's test days in a file: `herd_lactations` with `path` (or `csv_text`). One row per cow per test day.
- One cow you have the test days for: `lactation`.
- Whether a cow is giving what she should today: `expected_curve`, then compare her latest test with the curve at
  that day in milk.
- USDA's age factors on their own: `mature_equivalent_factors`.

## Getting the test days ready

The file needs a cow ID, lactation number, fresh (calving) date, days in milk (or the test date) and milk. Fat %,
protein % and somatic cell score (linear score) improve the record when they are there. Column names are matched
loosely, so a DHI or DairyComp export usually works as it is: `ID`, `LACT`, `FDAT`, `DIM` or `TDAT`, `MILK`, `PCTF`,
`PCTP`, `SCS`.

- For mature equivalent, the file needs each cow's age at calving in months (`AGE`), and the call needs the farm's
  `state` (a 2-letter postal code such as CA). Without both, the records are actual yields only; say so.
- Give the herd's 305-day mature-equivalent averages (`herd_milk`, `herd_fat`, `herd_protein`) when they are known;
  without them the breed average is used.
- Pounds unless the farm works in kilograms (`units: "kg"`).

## Reading the results

- **305-day milk (actual)**: what the cow is projected to give in 305 days, from the tests so far.
- **Mature equivalent**: the same, adjusted to a mature cow calving in the same month and region, so cows of different
  ages compare fairly.
- **Reliability**: how much of the record rests on her own tests rather than the herd and breed. Few tests early in
  lactation mean low reliability; say so beside the number.
- **Persistency**: how well she holds her milk after peak, in standard deviations; 0 is average, negative drops faster.

Report the numbers with their units and reliability. Don't round them further or add targets the tools did not give.
