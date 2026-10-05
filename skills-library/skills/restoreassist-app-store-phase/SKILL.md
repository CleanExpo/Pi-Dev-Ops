---
name: restoreassist-app-store-phase
description: Use when working on any App Store or Google Play submission task for RestoreAssist — enrollment, certificates, store listings, testing tracks, or release submission
---

# RestoreAssist — App Store Submission Phase

## Overview

Complete reference for submitting RestoreAssist to both Apple App Store and Google Play Store. Covers enrollment, signing, listings, and submission.

## Accounts & Identity

| Field | Value |
|---|---|
| **Google Play account** | `airestoreassist@gmail.com` |
| **Google Play developer name** | "Restore Assist" (space — "RestoreAssist" taken) |
| **Apple enrollment URL** | `developer.apple.com/programs/enroll/` |
| **Legal entity** | UNITE-GROUP NEXUS PTY LTD |
| **ABN** | 95 691 477 844 |
| **ACN** | 691477844 |
| **D-U-N-S** | 775125643 |
| **D&B address propagation** | ~2026-04-15 (submitted via illion 2026-04-08) |

## Android Signing

| Field | Value |
|---|---|
| **Keystore file** | `C:\Users\Disaster Recovery 4\RestoreAssist-keystores\cet-release.jks` |
| **Keystore password** | `CETRelease2026!` |
| **Key alias** | `cet-release` (confirm via `keytool -list -v -keystore <path>`) |

## Phase Task Checklist

### Stage 1 — Unblock Enrollment (waiting ~2026-04-15)

- [ ] **Apple**: Receive D&B address confirmation email → D-U-N-S 775125643 fully verified
- [ ] **Google Play**: Confirm `airestoreassist@gmail.com` Play Console identity review complete
  - Access: Chrome → top-right avatar → Add account → `airestoreassist@gmail.com`
  - If still at step 4: enter D-U-N-S `775125643`
  - Remaining steps after D-U-N-S: Your organisation, Public developer profile, About you, Apps, How Google contacts you, Terms

### Stage 2 — Apple Developer Enrollment

1. Go to `developer.apple.com/programs/enroll/`
2. Sign in with Apple ID (likely `airestoreassist@gmail.com` — verify which account)
3. Select **Organisation** (not Individual)
4. Enter D-U-N-S `775125643` → Legal name: UNITE-GROUP NEXUS PTY LTD
5. Pay **$149 AUD**
6. Wait for approval email (typically 24–48 hrs)

### Stage 3 — iOS Certificate & Provisioning Profile

After Apple enrollment approved:

```bash
# 1. Create Certificate Signing Request (CSR) on Mac
# Keychain Access → Certificate Assistant → Request Certificate from CA
# Save to disk as RestoreAssist_CSR.certSigningRequest

# 2. In Apple Developer portal:
#    Certificates → + → Apple Distribution → upload CSR → download .cer

# 3. Install .cer into Keychain, then export as .p12
# Keychain → right-click cert → Export → save as RestoreAssist_Dist.p12

# 4. Convert to base64 for GitHub/Vercel secret
base64 -i RestoreAssist_Dist.p12 | pbcopy   # macOS
# or on Windows (PowerShell):
[Convert]::ToBase64String([IO.File]::ReadAllBytes("RestoreAssist_Dist.p12")) | clip

# 5. Create Provisioning Profile in Apple Developer portal:
#    Profiles → + → App Store → select App ID → select cert → download .mobileprovision
base64 -i RestoreAssist.mobileprovision | pbcopy
```

**GitHub/Vercel secrets to set:**
| Secret | Value |
|---|---|
| `IOS_CERTIFICATE_BASE64` | Base64 of .p12 |
| `IOS_CERTIFICATE_PASSWORD` | Password you set on export |
| `IOS_PROVISIONING_PROFILE_BASE64` | Base64 of .mobileprovision |
| `IOS_BUNDLE_ID` | `com.restoreassist.app` (confirm in Xcode/Capacitor config) |

### Stage 4 — Android Store Listing (Google Play)

After Play Console signup complete:

1. Create app: **Apps → Create app**
2. App name: "RestoreAssist — Water Damage Compliance"
3. Default language: English (Australia)
4. App or game: **App**
5. Free or paid: **Free**
6. Fill **Store listing**:
   - Short description (80 chars): "IICRC-compliant water damage restoration platform for Australian professionals"
   - Full description: See `distribution/store-listings.md` in repo
   - Screenshots: Pull from `distribution/screenshots/` (already generated)
   - Feature graphic: 1024×500 px from `distribution/assets/`
7. Set up **Closed testing track** (Internal or Alpha):
   - 14-day test period, minimum 12 testers
   - Add testers: invite via email
8. Upload AAB: run `android-release.yml` GitHub Action → download `app-release.aab`
9. Complete **Content rating** questionnaire
10. Complete **Data safety** section

### Stage 5 — Apple App Store Listing (App Store Connect)

After IPA built by `ios-release.yml`:

1. Go to `appstoreconnect.apple.com`
2. **Apps → +** → New App
3. Name: "RestoreAssist"
4. Bundle ID: match Capacitor config
5. SKU: `com.restoreassist.app`
6. Fill **App Information**, **Pricing**, **App Privacy**
7. Upload screenshots (6.7", 5.5", iPad 12.9") from `distribution/screenshots/`
8. Submit for **TestFlight** beta first → invite 14 testers
9. After beta approval → submit for **App Review**

### Stage 6 — CI/CD Verification

Both GitHub Actions workflows are already fixed:

| Workflow | File | Trigger |
|---|---|---|
| Android | `android-release.yml` | Tag `v*` push or manual |
| iOS | `ios-release.yml` | Tag `v*` push or manual |

**To trigger a build:**
```bash
git tag v1.1.0 && git push origin v1.1.0
```

**Distribution files:**
- `distribution/whatsnew/en-AU` and `en-US` — already created
- `distribution/store-listings.md` — full listing copy

## Gmail Monitoring

The Gmail MCP connector is linked to `phill.mcgurk@gmail.com`. Key emails will arrive at:
- `airestoreassist@gmail.com` — Google Play identity review result
- Possibly `phill.mcgurk@gmail.com` or `phill_bron@hotmail.com` — Apple D-U-N-S confirmation

**Check manually** at those accounts until MCP connector is re-authenticated to the correct account.

Emails to watch for:
- From `@dnb.com` or `@illion.com.au`: D-U-N-S address confirmation
- From `@developer.apple.com`: Enrollment approval
- From `@google.com` subject "Google Play Developer identity verification"

## Support Page

`/support` page already created at `restoreassist.com.au/support` — required by Apple App Store guidelines (Rule 2.5.7).

## Common Mistakes

| Mistake | Fix |
|---|---|
| Using `phill.mcgurk@gmail.com` for Play Console | Wrong account — use `airestoreassist@gmail.com` |
| Selecting "Individual" for Apple | Must be "Organisation" to use D-U-N-S |
| Uploading APK instead of AAB | Play Console requires AAB since 2021 |
| Wrong D-U-N-S number | Always `775125643` (Unite-Group Nexus, not Disaster Recovery) |
| iOS cert password mismatch | Use the EXACT password set during p12 export for `IOS_CERTIFICATE_PASSWORD` |
