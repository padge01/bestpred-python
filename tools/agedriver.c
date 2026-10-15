/* Reference driver for the age factors: prints aiplage() and adjscs4() for a grid of cows, full precision.
   Build with USDA's aiplage.c and ageadjs.c (see tools/reference.sh); run where adjust.scs is. */
#include <stdio.h>

void aiplage(char *breed, short *agefrsh, short *fryear, short *frmonth, short *parity, short *state,
             short *doprev, short *agebase, double *agefacm, double *agefacf, double *agefacp);
int adjscs4(char *breed1, short *parity, short *month, short *state, short *age2, short *filler, short *scs);

int main(void) {
  const char *breeds = "ABGHJM";
  short states[] = {11, 23, 35, 42, 55, 64, 74, 85, 93, 96};
  short years[] = {1965, 1972, 1980, 1990, 2005, 2024};
  short bases[] = {0, 36};
  for (int b = 0; b < 6; b++)
    for (int s = 0; s < 10; s++)
      for (int y = 0; y < 6; y++)
        for (short parity = 1; parity <= 7; parity += 2)
          for (short month = 1; month <= 12; month += 5)
            for (short doprev = 0; doprev <= 360; doprev += 90)
              for (int k = 0; k < 2; k++) {
                char breed = breeds[b];
                short age = 14 + 13 * parity + (month % 7), state = states[s], year = years[y];
                short base = bases[k], dim = 305, scs = 329;
                double m, f, p;
                aiplage(&breed, &age, &year, &month, &parity, &state, &doprev, &base, &m, &f, &p);
                int adj = adjscs4(&breed, &parity, &month, &state, &age, &dim, &scs);
                printf("%c %d %d %d %d %d %d %d %.17g %.17g %.17g %d\n", breed, age, year, month, parity, state,
                       doprev, base, m, f, p, adj);
              }
  return 0;
}
