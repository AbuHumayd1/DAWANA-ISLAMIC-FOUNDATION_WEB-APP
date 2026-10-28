# DIC QR camera compatibility correction

26 October 2026. **Follow-up verification passed:** required packages are installed, manifest/lockfile/installed versions agree, real ZXing image-decoding checks pass and the user-produced build contains the bundled fallback. The earlier installation/build blockers below are historical and resolved. No real-device camera pass is claimed.

The user's confirmation that all 21 backend tests passed and movement migration 0001 was applied is accepted as prior evidence. No backend, database, migration or permission changes occurred here.

## Root cause and correction

`CamperScanner.start()` previously returned before requesting the camera whenever native `BarcodeDetector` was absent or did not advertise `qr_code`. A functioning webcam does not imply this decoder API exists. The reported message came from that gate, not Django or a denied camera request.

The new decoder prefers native QR detection, with software fallback on missing/partial/rejected capability, constructor failure or native runtime failure. Healthy native no-code frames do not load software. Exact dependencies are declared for `@zxing/browser@0.2.1` and `@zxing/library@0.23.0`. The QR-only `BrowserQRCodeReader` is dynamically loaded in a local build chunk; no runtime CDN or image upload is used.

Camera ownership stays in the existing component: explicit Start/Stop, rear-facing preference with ordinary webcam compatibility, exact device selection and active-device reflection. Enumeration failure no longer stops a working camera. Permission denial, unavailable/occupied device, decoder-load failure and camera disconnection produce sanitized guidance. Tracks/decoders are disposed on stop, close, hiding, unmount and superseded starts; late async results are ignored/disposed. Manual token/link entry and participant search remain available. The existing visual frame/CSS was not redesigned.

Software decoding uses a reusable local canvas bounded to a 960px edge and the existing 250ms interval. Blank/checksum/format failures continue; unexpected errors stop safely. Tokens are not included in errors or logs. Successful detection still calls only the existing `action: preview` path. Arrival, departure and return retain their original explicit confirmations and backend permissions.

Upstream references: [ZXing browser project](https://github.com/zxing-js/browser), [versioned QR reader](https://github.com/zxing-js/browser/blob/v0.2.1/src/readers/BrowserQRCodeReader.ts), [canvas API](https://github.com/zxing-js/browser/blob/v0.2.1/src/readers/BrowserCodeReader.ts), [dependency declaration](https://github.com/zxing-js/browser/blob/v0.2.1/package.json).

## Initial checks before the user completed installation

```text
node --test src/services/checkIn.test.js src/services/camperMovement.test.js src/services/qrDecoder.test.js
20 passed; 0 failed; 0 skipped.

oxlint src/components/operations/CamperScanner.jsx src/services/qrDecoder.js src/services/qrFallback.js src/services/qrDecoder.test.js
Passed without warnings.

npm.cmd run build
Attempted, failed: unresolved @zxing/browser because package installation was denied.
```

Nine new tests cover native preference, software selection, native failure recovery, unready/empty frames, cancellation during loading, sanitized errors, bounded canvas capture/cleanup and camera-error guidance. They use injected decoder/reader doubles: **actual ZXing image decoding and webcam capture were not tested**. Eleven existing focused checks also passed. No full suite or backend tests repeated.

The npm registry download failed with EACCES, including a workspace-cache attempt. The default global cache was also inaccessible. No security/network settings were changed. Automatic approval review rejected removal of the task-created `dawana-platform/.npm-cache` as blocked by policy, so that temporary directory remains; it is not a runtime dependency.

**Packages are not installed and `package-lock.json` is unchanged.** `package.json` declares them, but the lockfile must be updated by normal installation before `npm ci`, build or deployment. Do not bypass the failed build by externalizing unresolved imports. An asynchronous request to perform installation in normal VS Code was sent; no success reply had arrived at report preparation.

## Commands requiring normal VS Code PowerShell

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP\dawana-platform"
npm.cmd install @zxing/browser@0.2.1 @zxing/library@0.23.0 --save-exact --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; do not bypass the build.' }
node --test src/services/checkIn.test.js src/services/camperMovement.test.js src/services/qrDecoder.test.js
if ($LASTEXITCODE -ne 0) { throw 'Focused tests failed.' }
.\node_modules\.bin\oxlint.cmd src/components/operations/CamperScanner.jsx src/services/qrDecoder.js src/services/qrFallback.js src/services/qrDecoder.test.js
if ($LASTEXITCODE -ne 0) { throw 'Affected-file lint failed.' }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Build failed; do not deploy.' }
```

Review/retain the generated lockfile and successful build output. No backend operations are needed.

## Exact files changed

1. `dawana-platform/package.json` — exact decoder dependencies.
2. `dawana-platform/src/components/operations/CamperScanner.jsx` — decoder integration, cleanup and camera error/selection handling; recording logic retained.
3. `dawana-platform/src/services/qrDecoder.js` — lazy native/software selection, lifecycle, canvas adapter and safe error guidance.
4. `dawana-platform/src/services/qrFallback.js` — QR-only ZXing adapter.
5. `dawana-platform/src/services/qrDecoder.test.js` — nine focused tests.
6. `scripts/DIC_2026_QR_CAMERA_COMPATIBILITY.md` — this report.

Temporary npm cache/log files are also retained as described above; no package-lock update succeeded.

## Real-device verification still required

1. After install/build, Chrome laptop without native BarcodeDetector: Start must open the webcam and software-decode a real issued QR into identity preview only.
2. Native-supported browser: verify native decoding and fallback recovery after native failures. Verify full QR URL/raw-token paste and manual participant search.
3. Real smartphone over approved HTTPS: rear camera, front/rear selection, autofocus/lighting/distance, portrait/landscape, existing frame/layout and scrolling. A phone cannot use the laptop's localhost address.
4. Deny permission; disconnect/occupy a camera; select a missing device; use insecure non-local HTTP; scan an invalid QR. Guidance must retain fallback options and reveal no tokens.
5. Stop/close/hide/change route or edition during startup, decoding and permission prompts. Confirm the hardware indicator turns off and no late stream/result survives. Repeat start/stop and camera switching.
6. Verify arrival/departure/return still require explicit authorized confirmation. For development camera checks, preview an existing authorized ID without confirming any action; synthetic movement writes belong only in isolation.

The native-only restriction is corrected in source. The follow-up below resolves dependency/lockfile/build availability; real-device acceptance remains required.

## Follow-up after installation

The user installed both dependencies and completed a production build. Executed verification confirmed:

- `npm ls --depth=0`: `@zxing/browser` **0.2.1**, `@zxing/library` **0.23.0**. Manifest declarations, lockfile root declarations, resolved package entries and installed package versions all agree. Both lock entries have registry URLs and integrity values. Browser's `^0.23.0` peer requirement is satisfied.
- Installed peer relationships were checked with `npm ls @zxing/library --all`.
- Existing build artifact `dist/assets/qrFallback-CPV6L-H_.js` is bundled (477,736 bytes before compression), contains no unresolved ZXing bare import, and is dynamically referenced by the production main bundle. This verifies the available output; the user's successful build was not rerun unnecessarily. The fallback is a substantial optional chunk, not part of the initial decoder path.
- Added `src/services/qrFallback.integration.test.js`: **two new tests passed, no skips**, using real installed ZXing engines via the Vite module loader and a synthetic in-memory canvas. A generated camper-format QR URL was decoded exactly through the production fallback import/factory. A blank image returned no result using actual ZXing no-code exception handling. Canvas cleanup and decode-after-disposal were also checked.
- New test-file lint passed. Previously passing 20 focused checks and application lint were not repeated because no application source changed in this follow-up. Two initial new-test harness issues (Node/CommonJS named-export handling and required writer hints) were corrected before the passing run; no scanner defect was found.
- Vite SSR emitted upstream ZXing source-map path warnings. They did not prevent the tests from passing; they are not camera decoding failures.

Files changed **in this follow-up**: `dawana-platform/src/services/qrFallback.integration.test.js` and this report. The package installation/lockfile changes were made by the user and verified, not attributed to this follow-up. No backend, movement policy, migration, permission or database changes occurred.

### Exact browser acceptance sequence

1. Start/reuse the existing approved frontend/backend and sign in with an authorized Operations account. Open `/dic/operations/check-in`, choose the correct edition and click **Scan ID**. Do not click a movement confirmation during development camera-only acceptance.
2. Before **Start camera**, confirm no camera permission prompt or hardware indicator. Click Start, allow permission and point the laptop webcam at a valid authorized camper card on another screen/paper. Expect camera preview and one identity preview, camera stopped after detection, and no automatic arrival/departure/return. Do not paste/share actual token values or screenshots containing the QR.
3. Verify the fallback in Chrome without native support. If native support exists, use DevTools Console on this tab before Start: `window.BarcodeDetector = undefined`, then Start. This is a temporary decoder-capability simulation; reload restores the normal page environment. In Network, expect the local fallback chunk to load successfully, with no request transmitting image frames. Expect the existing scan POST to use only `action: preview`.
4. Reload and test the native path on a device that reports native `qr_code` support. Verify a real QR again and check the fallback chunk is not needed for a healthy native reader. A previously cached chunk being present is not proof of which engine ran; inspect requests on a fresh reload with cache disabled.
5. If multiple cameras are listed, choose each one. Verify the preview changes and only one capture remains active. Test a laptop webcam and a phone over a reachable approved HTTPS origin. On the phone verify rear-camera preference, front/rear selection where exposed, portrait/landscape, focus, lighting, frame visibility and scrolling.
6. Stop, restart, close the scanner, switch edition/route and hide the tab. Repeat while permission/startup is pending. Expect the camera indicator to turn off, no stale preview, and no late stream restarting itself.
7. Deny permission; test an occupied/disconnected camera and invalid QR. Expect appropriate guidance, no tokens in errors, and working paste/manual-search fallback. An insecure non-local HTTP page should explain the HTTPS requirement.
8. Verify action permissions/confirmations using the approved isolated test facility: detection must never record movement; initial arrival/departure/return each require the existing explicit action, and departure retains its release-authority checks. No synthetic development movement records are authorized by this camera check.

Recommendation: **ready for real-browser camera acceptance**, not yet verified as working on a real webcam/phone. No production-readiness claim follows from the in-memory decoding tests.
