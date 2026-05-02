import { BrandColour } from '../brands/types';

/** Convert hex (#RRGGBB) to relative luminance per WCAG. */
function relLum(hex: string): number {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio between two hex colours. >= 4.5 is AA for normal text. */
export function contrast(a: string, b: string): number {
  const la = relLum(a);
  const lb = relLum(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Returns whichever of brand.neutral.50 or brand.neutral.900 has best contrast against bg. */
export function readableOn(bg: string, palette: BrandColour): string {
  const light = palette.neutral['50'];
  const dark = palette.neutral['900'];
  return contrast(bg, dark) >= contrast(bg, light) ? dark : light;
}

/** Compose a CSS gradient from primary → secondary at given angle. */
export function brandGradient(palette: BrandColour, angleDeg: number = 135): string {
  return `linear-gradient(${angleDeg}deg, ${palette.primary} 0%, ${palette.secondary} 100%)`;
}
