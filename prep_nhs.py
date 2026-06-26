"""
prep_nhs.py
-----------
Minimal data prep for the NHS GP Appointments Power BI dashboard.

Everything that *showcases* BI skill (DNA-rate measures, relationships, the
star schema) is built in Power BI. This script only does the unglamorous prep
that's tedious by hand and is honest "data preparation":

  1. dim_geography.csv     icb_ons_code -> region_ons_code -> region_name
                           (the readable region names the raw data lacks)
  2. dim_wait_band.csv     wait band  -> numeric sort order
  3. dim_duration_band.csv duration band -> numeric sort order
                           (so Power BI sorts "2 to 7 Days" before "15 to 21",
                            not alphabetically)

Band sort orders are derived from the band TEXT itself, so they match the
files exactly regardless of dashes/spacing. Run from the project folder:

    python prep_nhs.py
"""
import re
from pathlib import Path

import pandas as pd

DATA = Path("data")

# Verified NHS England region ONS codes -> names. The data spans Jan 2020 –
# Jun 2022 and straddles the July 2022 boundary refresh, so Midlands and
# North East and Yorkshire each appear under BOTH their old and new codes;
# both are mapped to the same name so they consolidate.
REGION_NAMES = {
    "E40000003": "London",
    "E40000005": "South East",
    "E40000006": "South West",
    "E40000007": "East of England",
    "E40000008": "Midlands",                    # pre-Jul 2022
    "E40000011": "Midlands",                    # Jul 2022 reissue
    "E40000009": "North East and Yorkshire",    # pre-Jul 2022
    "E40000012": "North East and Yorkshire",    # Jul 2022 reissue
    "E40000010": "North West",
}


def band_sort(label: str) -> int:
    """Numeric order from a band label's own text.
    'Same Day'->0, 'More than 28 Days'->99-ish via its number, 'Unknown'->999."""
    s = str(label)
    if re.search(r"unknown|data quality", s, re.I):
        return 999
    if re.search(r"same day", s, re.I):
        return 0
    nums = re.findall(r"\d+", s)
    return int(nums[0]) if nums else 998   # first number = natural order


def main() -> None:
    appts = pd.read_csv(DATA / "appointments_regional.csv")
    dur = pd.read_csv(DATA / "actual_duration.csv")

    # --- 1. Geography dimension (one row per icb_ons_code) ----------------
    # actual_duration carries the hierarchy; roll it up to ICB grain.
    geo = (dur[["icb_ons_code", "region_ons_code"]]
           .dropna().drop_duplicates())

    # Guard: each ICB should sit in exactly one region.
    dupes = geo.groupby("icb_ons_code")["region_ons_code"].nunique()
    if (dupes > 1).any():
        print("  ! some ICBs map to >1 region; keeping the first seen")
        geo = geo.drop_duplicates(subset="icb_ons_code")

    # Include any ICB codes that appear in appointments but not in duration.
    appt_icbs = set(appts["icb_ons_code"].dropna().unique())
    missing = appt_icbs - set(geo["icb_ons_code"])
    if missing:
        print(f"  ~ {len(missing)} ICB code(s) in appointments have no region "
              f"in the duration file; region set to Unknown")
        geo = pd.concat([geo, pd.DataFrame(
            {"icb_ons_code": list(missing), "region_ons_code": pd.NA})],
            ignore_index=True)

    geo["region_name"] = geo["region_ons_code"].map(REGION_NAMES)

    unmapped = sorted(geo.loc[geo["region_name"].isna()
                              & geo["region_ons_code"].notna(),
                              "region_ons_code"].unique())
    if unmapped:
        print(f"  ! unmapped region codes (left as code): {unmapped}")
    geo["region_name"] = geo["region_name"].fillna(
        geo["region_ons_code"]).fillna("Unknown")

    geo = geo.sort_values("icb_ons_code")
    geo.to_csv(DATA / "dim_geography.csv", index=False)

    # --- 2 & 3. Band-order lookups (read actual values from the files) ----
    wait_col = "time_between_book_and_appointment"
    waits = pd.DataFrame({wait_col: sorted(appts[wait_col].dropna().unique())})
    waits["wait_band_order"] = waits[wait_col].map(band_sort)
    waits.sort_values("wait_band_order").to_csv(
        DATA / "dim_wait_band.csv", index=False)

    dur_col = "actual_duration"
    durs = pd.DataFrame({dur_col: sorted(dur[dur_col].dropna().unique())})
    durs["duration_band_order"] = durs[dur_col].map(band_sort)
    durs.sort_values("duration_band_order").to_csv(
        DATA / "dim_duration_band.csv", index=False)

    # --- Verification summary --------------------------------------------
    print("\n=== dim_geography.csv ===")
    print(f"  {len(geo)} ICBs across {geo['region_name'].nunique()} regions")
    print("  regions:", sorted(geo["region_name"].unique()))
    print("\n=== dim_wait_band.csv ===")
    print(waits.sort_values("wait_band_order").to_string(index=False))
    print("\n=== dim_duration_band.csv ===")
    print(durs.sort_values("duration_band_order").to_string(index=False))
    print("\nWrote 3 lookup files to ./data/")


if __name__ == "__main__":
    main()
