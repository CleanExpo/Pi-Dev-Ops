/** Unite-Group Nexus brand tokens. Duplicated here from
 * Pi-Dev-Ops/packages/brand-config until that package is workspace-linkable.
 * TODO: replace with `import { UNITE_GROUP } from "@unite-group/brand-config"`. */

export const BRAND = {
  name: "Unite Group Nexus",
  colors: {
    background: "#0e1014", // Gun Metal
    surface: "#15181f",
    hairline: "#2a2d35",
    textPrimary: "#f4ecd8", // warm cream
    textMuted: "#8c8a85",
    accent: "#b30000", // Candy Red
    accentMuted: "#7a0000",
  },
  fonts: {
    body: 'Inter, -apple-system, system-ui, sans-serif',
    brand: 'Charter, "Iowan Old Style", Georgia, serif',
    mono: '"SF Mono", Menlo, Consolas, monospace',
  },
} as const;
