// Zero-padded state_fips(2)/county_fips(3) join key, matching the
// convention used throughout the Python pipeline (src/config.py STATES,
// every table/CSV in the project). Census TIGER properties (STATEFP/
// COUNTYFP) already come zero-padded, but normalize defensively so a county
// key built from either source always matches.

export function stateFips(value: string | number): string {
  return String(value).padStart(2, "0");
}

export function countyFips(value: string | number): string {
  return String(value).padStart(3, "0");
}

export function countyKey(state: string | number, county: string | number): string {
  return `${stateFips(state)}-${countyFips(county)}`;
}
