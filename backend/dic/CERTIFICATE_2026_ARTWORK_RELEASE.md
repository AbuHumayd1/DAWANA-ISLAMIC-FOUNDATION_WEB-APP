# DIC 2026 certificate — final approved copy and release safeguard

## Owner-approved certificate artwork

Based on the designer-provided **3264 × 2522 JPEG** (not an AI replacement), the artwork is corrected to read:

**Issued under the authority of**

Left:
- **Shaykh AbdulHakeem Yuusuf Olomoda**
- **Ameer**
- **Da’wānā Islamic Foundation**

Right:
- **Brother Abdullah Salman Akinola**
- **Camp Director**
- **Darul Islam Camp 2026**

No handwritten signatures are claimed or simulated.

Corrected image: `backend/dic/assets/certificates/DIC_2026_certificate_approved_artwork.jpg`
Expected SHA-256: `bcbcf0615b11c7ebf7447de969b2f64966f7314d940a1377c2a628816cf60008`
Exact dimensions: 3264 × 2522 pixels.
**The image must be installed at this exact path with the exact checksum.** If absent, the preparatory command refuses to configure it; issuance stays blocked.

## Reviewed positions

- Page size: 842 × 651 PDF points (the original artwork ratio).
- Participant name: [151, 290, 540, 54] (PDF points; bottom-left origin).
- Unique certificate reference: [230, 15, 382, 25].
- Name and reference placements are testable without opening public access.

## Deployment sequence

1. Commit the corrected designer JPEG binary to the path above.
2. Verify SHA-256 matches.
3. Run `python manage.py configure_dic2026_certificate` for a read-only check.
4. Run `python manage.py configure_dic2026_certificate --apply` to save *disabled* configuration.
5. Verify preview quality for long participant names, positional overlap, document aspect ratio and PDF text extraction; the submitted preview must not be mistaken for a valid issued certificate.
6. Explicitly enable release only after successful QA and owner sign-off. Even with enabled=True, the server never allows issuance before **31 December 2026, 21:00 Africa/Lagos**.
7. Physical camp check-in and authenticated entitlement are still mandatory. Issuance remains individually audited with stable unique references and revocation.

No private participant data, false signatures, new migration or additional hosting service is required. Do not change paid-order access, or enable the certificates earlier.
