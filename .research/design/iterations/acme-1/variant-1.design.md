---
version: alpha
name: Acme — Stripe-precision-with-mono-rigour
description: Trust-led B2B SaaS for ML engineers. Tight typography, minimal palette, mono accents for technical credibility.
colors:
  primary: "#0F172A"
  secondary: "#1E293B"
  accent: "#22D3EE"
  neutral-50: "#F8FAFC"
  neutral-100: "#E2E8F0"
  neutral-500: "#64748B"
  neutral-900: "#020617"
  success: "#10B981"
  warning: "#F59E0B"
  danger: "#EF4444"
  on-primary: "#F8FAFC"
  on-secondary: "#F8FAFC"
  on-accent: "#020617"
  surface: "{colors.neutral-50}"
  on-surface: "{colors.neutral-900}"
typography:
  display-xl:
    fontFamily: Inter
    fontSize: 80px
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: -0.03em
  display-lg:
    fontFamily: Inter
    fontSize: 56px
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: -0.02em
  display-md:
    fontFamily: Inter
    fontSize: 40px
    fontWeight: 700
    lineHeight: 1.1
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.55
  body-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.55
  caption:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
  mono-md:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.4
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  outer-margin-landscape: 96px
  outer-margin-portrait: 64px
rounded:
  sm: 4px
  DEFAULT: 6px
  md: 8px
  lg: 12px
  full: 9999px
components:
  cta-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.primary}"
    rounded: "{rounded.DEFAULT}"
    padding: "{spacing.md}"
    typography: "{typography.body-lg}"
  card:
    backgroundColor: "{colors.secondary}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
---

## Overview

Stripe-grade precision applied to MLOps. Dark slate canvas with cyan signal accent.
