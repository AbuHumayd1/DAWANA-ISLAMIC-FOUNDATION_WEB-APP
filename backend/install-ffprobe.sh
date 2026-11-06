#!/usr/bin/env bash
# Optional Render build step only. The owner supplies an approved raw Linux binary
# URL and SHA-256; there is no guessed release, archive extraction or package install.
set -euo pipefail
cd "$(dirname "$0")"
: "${DIC_FFPROBE_DOWNLOAD_URL:?Approve a public HTTPS raw ffprobe binary URL}"
: "${DIC_FFPROBE_SHA256:?Approve its exact SHA-256}"
[[ "$DIC_FFPROBE_DOWNLOAD_URL" == https://* ]] || exit 1
[[ "$DIC_FFPROBE_SHA256" =~ ^[a-fA-F0-9]{64}$ ]] || exit 1
command -v curl >/dev/null
command -v sha256sum >/dev/null
artifact=$(mktemp)
trap 'rm -f "$artifact"' EXIT
if ! curl --silent --fail --location --proto '=https' --proto-redir '=https' \
    --max-time 120 --max-filesize 100000000 "$DIC_FFPROBE_DOWNLOAD_URL" -o "$artifact" 2>/dev/null; then
    echo 'Approved ffprobe artifact could not be retrieved.' >&2
    exit 1
fi
printf '%s  %s\n' "$DIC_FFPROBE_SHA256" "$artifact" | sha256sum --check --status
mkdir -p .runtime
install -m 0755 "$artifact" .runtime/ffprobe
.runtime/ffprobe -version >/dev/null
