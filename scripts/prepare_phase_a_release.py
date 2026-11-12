"""Reproducible offline source candidate. Never stages, commits, pushes or deploys.

Uses a committed local baseline plus the enumerated Phase A and previous
production-correction overlays. This is NOT proof of the deployed baseline.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '7a9c97845541c56820380b9756eac4c4c5eeb093'
EXCLUDED_PREFIXES = ('.dic-refs/', '.home-ref/', '.home-strict-ref/', '.page-refs/',
    'stitch-designs/', 'backups/', 'acceptance-artifacts/', 'validation-results/')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def normalize(data):
    return data.replace(b'\r\n', b'\n') if b'\0' not in data else data


def workspace_evidence():
    status = git('status', '--porcelain=v1', '-uall').decode('utf-8')
    tracked = git('ls-files', '-z').decode().split('\0')
    untracked = git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
    return dict(status=status, files={p: sha((ROOT/p).read_bytes()) for p in sorted(set(tracked+untracked))
        if p and (ROOT/p).is_file()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    destination = Path(args.destination).resolve()
    if not destination.is_relative_to(ROOT / 'output') or destination.exists():
        raise RuntimeError('Choose a new destination within workspace output; overwrite refused.')
    if git('rev-parse', 'HEAD').decode().strip() != BASE:
        raise RuntimeError('Local baseline changed; review before packaging.')
    before = workspace_evidence()
    report = (ROOT/'DAWANA_PHASE_A_IMPLEMENTATION_REPORT.md').read_text(encoding='utf-8')
    inventory = report.split('## 3. Exact application/test files changed', 1)[1].split('## 4.', 1)[0]
    phase_a = [p for block in re.findall(r'```text\n(.*?)```', inventory, re.S) for p in block.splitlines() if p.strip()]
    prior = json.loads((ROOT/'release-validation/release-manifest.json').read_text())
    if prior['base_commit'] != BASE:
        raise RuntimeError('Previous production-correction baseline differs.')
    correction = [row['path'] for row in prior['files']]
    extra = ['DAWANA_PHASE_A_PRODUCTION_PREFLIGHT.md', 'scripts/prepare_phase_a_release.py',
        'scripts/validate_phase_a_candidate.py']
    overlays = sorted(set(phase_a+correction+extra))
    data = {}
    excluded = []
    archive = zipfile.ZipFile(io.BytesIO(git('archive', '--format=zip', BASE)))
    for info in archive.infolist():
        if info.is_dir():
            continue
        if info.filename.startswith(EXCLUDED_PREFIXES):
            excluded.append(info.filename)
        else:
            data[info.filename] = archive.read(info)
    for path in overlays:
        if path.startswith(EXCLUDED_PREFIXES) or not (ROOT/path).is_file():
            raise RuntimeError('Invalid overlay: '+path)
        data[path] = normalize((ROOT/path).read_bytes())
    # The earlier checkout feedback regression predates the owner's explicit
    # acceptance of numeric/common passwords. Preserve its original in the
    # working tree; in this candidate test the genuinely invalid EMPTY password
    # exercises the same nested-error/no-side-effect contract.
    policy_test = 'backend/dic/test_checkout_validation.py'
    original_test = data[policy_test]
    corrected_test = original_test.replace(
        b'test_numeric_password_returns_nested_account_error_before_order_or_payment_creation',
        b'test_empty_password_returns_nested_account_error_before_order_or_payment_creation').replace(
        b"password='123456789012', password_confirmation='123456789012'", b"password='', password_confirmation=''").replace(
        b"self.assertIn('entirely numeric', str(errors['portal_account']))", b"self.assertIn('blank', str(errors['portal_account']))")
    if corrected_test == original_test:
        raise RuntimeError('Review changed older checkout-policy regression before packaging.')
    data[policy_test] = corrected_test
    # Git's archived baseline contains CRLF font text while its committed
    # provenance hashes identify LF originals. Restore ONLY hash-verified
    # canonical bytes; do not rewrite the provenance metadata or waive its test.
    font_root = 'dawana-platform/public/'
    provenance = json.loads(data[font_root+'fonts/sources.json'])
    font_text = [('fonts.css', provenance['local_css_sha256'])] + [
        ('fonts/'+row['name'], row['sha256']) for row in provenance['files'] if row['name'].endswith('.txt')]
    canonicalized = []
    for relative, expected in font_text:
        path = font_root + relative
        if sha(data[path]) == expected:
            continue
        canonical = normalize(data[path])
        if sha(canonical) != expected:
            raise RuntimeError('Font provenance mismatch beyond line endings: '+path)
        data[path] = canonical
        canonicalized.append(path)
    files = [dict(path=p, size=len(value), sha256=sha(value),
        origin='phase-a-policy-test-alignment' if p == policy_test else 'canonical-font-provenance' if p in canonicalized else 'phase-a' if p in phase_a else 'prior-production-correction' if p in correction else
        'release-preparation' if p in extra else 'committed-baseline') for p,value in sorted(data.items())]
    identity = sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
    destination.mkdir(parents=True)
    source = destination/'source'
    source.mkdir()
    for path, value in sorted(data.items()):
        target = source/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    zip_path = destination/'phase-a-source.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path,value in sorted(data.items()):
            info=zipfile.ZipInfo(path, date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o100755 if path.endswith('.sh') else 0o100644) << 16
            output.writestr(info,value)
    manifest=dict(format=1, candidate_id=identity, base_commit=BASE,
        deployed_base_verified=False, archive_sha256=sha(zip_path.read_bytes()),
        phase_a_overlays=phase_a, prior_correction_overlays=correction,
        preparation_overlays=extra, excluded_committed_reference_files=excluded,
        canonicalized_font_text=canonicalized,
        policy_test_alignment=dict(path=policy_test, original_sha256=sha(original_test),
            candidate_sha256=sha(corrected_test), reason='Empty passwords are invalid; numeric passwords are owner-approved.'),
        dependency_files={p:sha(data[p]) for p in ('backend/requirements.txt',
            'backend/requirements-test-ids.txt','backend/constraints-staging.txt',
            'dawana-platform/package.json','dawana-platform/package-lock.json')}, files=files)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (destination/'workspace-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
    after=workspace_evidence()
    if after != before:
        raise RuntimeError('Workspace changed during packaging. Inspect; no work has been reverted.')
    (destination/'workspace-preserved.json').write_text(json.dumps(dict(verified=True,
        tracked_and_untracked_files=len(before['files'])),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate_id=identity, archive_sha256=manifest['archive_sha256'],
        files=len(files), overlays=len(overlays), destination=str(destination)),indent=2))


if __name__ == '__main__':
    main()
