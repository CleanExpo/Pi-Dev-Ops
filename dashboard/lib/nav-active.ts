/** True when `pathname` is this nav href or a nested route under it. */
export function pathMatchesNav(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Control subnav: Live is exact `/control` only; other tabs match themselves and children. */
export function controlTabActive(pathname: string, href: string): boolean {
  if (href === "/control") return pathname === "/control";
  return pathMatchesNav(pathname, href);
}
