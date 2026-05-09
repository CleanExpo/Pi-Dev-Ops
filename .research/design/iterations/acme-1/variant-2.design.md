---
version: alpha
name: Acme — Linear-clarity
description: Light-mode-first B2B SaaS. Generous spacing, restrained accent, editorial typography.
colors:
  primary: "#5E6AD2"
  secondary: "#1F2937"
  accent: "#F472B6"
  neutral-50: "#FFFFFF"
  neutral-100: "#F3F4F6"
  neutral-500: "#6B7280"
  neutral-900: "#111827"
  success: "#10B981"
  warning: "#F59E0B"
  danger: "#EF4444"
  on-primary: "#FFFFFF"
  on-secondary: "#FFFFFF"
  on-accent: "#111827"
  surface: "{colors.neutral-50}"
  on-surface: "{colors.neutral-900}"
typography:
  display-xl:
    fontFamily: Inter
    fontSize: 96px
    fontWeight: 600
    lineHeight: 1.0
    letterSpacing: -0.04em
  display-lg:
    fontFamily: Inter
    fontSize: 64px
    fontWeight: 600
    lineHeight: 1.05
  display-md:
    fontFamily: Inter
    fontSize: 44px
    fontWeight: 600
    lineHeight: 1.1
  body-lg:
    fontFamily: Inter
    fontSize: 19px
    fontWeight: 400
    lineHeight: 1.6
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  caption:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 32px
  xl: 56px
  2xl: 80px
  outer-margin-landscape: 120px
  outer-margin-portrait: 64px
rounded:
  sm: 6px
  DEFAULT: 10px
  md: 14px
  lg: 20px
  full: 9999px
components:
  cta-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-50}"
    rounded: "{rounded.DEFAULT}"
    padding: "{spacing.md}"
    typography: "{typography.body-lg}"
  card:
    backgroundColor: "{colors.neutral-50}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
---

## Overview

Linear-grade clarity. Generous breathing space, indigo primary, soft pink accent for signal moments.
