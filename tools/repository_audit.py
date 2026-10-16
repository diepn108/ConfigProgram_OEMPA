"""Read-only source-distribution audit. Never imports the OEM-PA API or deletes files."""

from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOTS = {'artifacts', 'data', 'dll', '.git', '.venv', 'venv', '.vscode', '.idea'}
GENERATED = {'gui_ascan_config.txt', 'gui_fmc_config.txt', 'backend_full_test.txt', 'fmc16_generated.txt',
             'multichannel_readback.txt', 'multichannel_2tx_readback.txt', 'pa_test_30deg_aos_roundtrip.txt'}
BUILD_SUFFIXES = {'.pyc', '.pyo', '.dll', '.obj', '.exp', '.lib', '.pdb', '.ilk', '.exe', '.log', '.tmp', '.bak'}


def distribution_files(root=ROOT):
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.as_posix() == 'data/README.md':
            yield path
            continue
        if relative.parts[0] in LOCAL_ROOTS or any(part.startswith('.') and part not in {'.gitignore'} for part in relative.parts):
            continue
        if '__pycache__' in relative.parts or path.suffix.lower() in BUILD_SUFFIXES or path.name == 'cl':
            continue
        if relative.parts[0] == 'configs' and path.name in GENERATED:
            continue
        if path.name.startswith('.env') or path.suffix.lower() in {'.pem', '.key'}:
            continue
        yield path


def audit(root=ROOT):
    files = sorted(distribution_files(root))
    patterns = {'personal_absolute_path': re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+'),
                'private_key': re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----'),
                'access_key': re.compile(r'AKIA[0-9A-Z]{16}'),
                'api_key': re.compile(r'sk-[A-Za-z0-9]{32,}')}
    candidates = []
    for path in files:
        try:
            source = path.read_text(encoding='utf-8')
        except (UnicodeError, OSError):
            candidates.append({'file': path.relative_to(root).as_posix(), 'kind': 'unreadable_source'})
            continue
        for number, line in enumerate(source.splitlines(), 1):
            for kind, pattern in patterns.items():
                if pattern.search(line):
                    candidates.append({'file': path.relative_to(root).as_posix(), 'line': number, 'kind': kind})
    return {'git_metadata_present': (root / '.git').exists(), 'source_files': len(files),
            'source_bytes': sum(p.stat().st_size for p in files),
            'extensions': dict(Counter(p.suffix or '(none)' for p in files)), 'candidates': candidates,
            'limitations': 'Filesystem/source allowlist review only; no Git history/index or exhaustive secret detection.'}


if __name__ == '__main__':
    report = audit()
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(report['candidates']))
