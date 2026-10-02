#!/usr/bin/env python3
"""Pack, verify and recover EdgeAI snapshots with Python's standard library.

No training, network or installation. Hashes detect corruption, not authorship.
Publication happens only after the new ZIP has passed full verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

MANIFEST = '_BUNDLE_MANIFEST.json'
MAX_BYTES = 1024 ** 3
EXCLUDED_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
                 '.mypy_cache', '.superpowers', 'build', 'dist'}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('unsafe archive path')
    parts = value.split('/')
    if any(not p or p in ('.', '..') or p.endswith((' ', '.')) for p in parts):
        raise ValueError('unsafe archive path')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('unsafe archive path')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {
        f'{name}{i}' for name in ('COM', 'LPT') for i in range(1, 10)}
    if any(p.split('.')[0].upper() in reserved for p in parts):
        raise ValueError('reserved archive path')
    return PurePosixPath(value)


def _inventory(source: Path) -> list[Path]:
    files = []
    for directory, dirs, names in os.walk(source, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith('build-'))
        for name in dirs + sorted(names):
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f'symlink is not distributable: {path}')
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(source).as_posix()
            if relative == MANIFEST or path.suffix in ('.pyc', '.pyo', '.partial'):
                continue
            if not path.is_file():
                raise ValueError(f'not a regular file: {path}')
            _safe_name(relative)
            files.append(path)
    return sorted(files)


def _zip_info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    return info


def _check_open(z: zipfile.ZipFile, max_bytes: int) -> dict:
    if max_bytes < 1:
        raise ValueError('invalid size limit')
    infos = z.infolist()
    names = [i.filename for i in infos]
    if not names or len(names) > 100000:
        raise ValueError('empty or excessive inventory')
    if len(set(n.casefold() for n in names)) != len(names):
        raise ValueError('duplicate inventory paths')
    total = 0
    for info in infos:
        _safe_name(info.filename)
        if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError('directory/symlink entry not allowed')
        if info.flag_bits & 1:
            raise ValueError('encrypted entries not supported')
        total += info.file_size
        if total > max_bytes:
            raise ValueError('uncompressed size limit exceeded')
    manifests = [n for n in names if n.endswith('/' + MANIFEST)]
    if len(manifests) != 1 or z.getinfo(manifests[0]).file_size > 16 * 1024 * 1024:
        raise ValueError('missing or excessive manifest')
    try:
        manifest = json.loads(z.read(manifests[0]))
        root = manifest['root']
        rows = manifest['files']
        if manifest['schema'] != 1 or len(_safe_name(root).parts) != 1 or not isinstance(rows, list):
            raise ValueError('unsupported manifest')
        if manifests[0] != root + '/' + MANIFEST:
            raise ValueError('root mismatch')
        expected = {root + '/' + MANIFEST}
        declared = set()
        for row in rows:
            name = row['path']; _safe_name(name)
            if name in declared or name == MANIFEST:
                raise ValueError('duplicate inventory')
            declared.add(name)
            expected.add(root + '/' + name)
            if type(row['bytes']) is not int or row['bytes'] < 0:
                raise ValueError('invalid size')
            if row['mode'] not in (0o644, 0o755):
                raise ValueError('invalid mode')
            digest = row['sha256']
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('invalid digest')
        if expected != set(names):
            raise ValueError('inventory mismatch')
        for row in rows:
            info = z.getinfo(root + '/' + row['path'])
            h = hashlib.sha256()
            with z.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            if info.file_size != row['bytes'] or h.hexdigest() != row['sha256']:
                raise ValueError('integrity mismatch: ' + row['path'])
            if (info.external_attr >> 16) & 0o777 != row['mode']:
                raise ValueError('integrity mode mismatch: ' + row['path'])
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid manifest') from exc
    return manifest


def verify(archive: Path, *, max_bytes: int = MAX_BYTES) -> dict:
    archive = Path(archive)
    try:
        with zipfile.ZipFile(archive) as z:
            manifest = _check_open(z, max_bytes)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError('invalid ZIP or integrity failure') from exc
    return {'archive': str(archive), 'root': manifest['root'],
            'files': len(manifest['files']), 'sha256': sha256_file(archive),
            'uncompressed_bytes': sum(row['bytes'] for row in manifest['files']),
            'status': 'verified'}


def pack(source: Path, archive: Path, *, replace: bool = False) -> dict:
    source = Path(source).resolve()
    archive = Path(archive).absolute()
    if not source.is_dir():
        raise ValueError('source must be an existing directory')
    if archive.resolve().is_relative_to(source):
        raise ValueError('archive must be outside source directory')
    if archive.is_symlink() or (archive.exists() and not replace):
        raise FileExistsError(str(archive))
    root = source.name; _safe_name(root)
    files = _inventory(source)
    if not files:
        raise ValueError('no files to pack')
    archive.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=archive.name + '.', suffix='.partial', dir=archive.parent)
    os.close(fd)
    tmp = Path(temporary)
    try:
        rows = []
        with zipfile.ZipFile(tmp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in files:
                relative = path.relative_to(source).as_posix()
                mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                info = _zip_info(root + '/' + relative, mode == 0o755)
                h = hashlib.sha256(); size = 0
                with path.open('rb') as src, z.open(info, 'w') as dest:
                    for block in iter(lambda: src.read(1024 * 1024), b''):
                        dest.write(block); h.update(block); size += len(block)
                rows.append({'path': relative, 'bytes': size, 'sha256': h.hexdigest(), 'mode': mode})
            payload = json.dumps({'schema': 1, 'root': root, 'files': rows}, ensure_ascii=False,
                                 sort_keys=True, indent=2).encode('utf-8') + b'\n'
            z.writestr(_zip_info(root + '/' + MANIFEST), payload)
        with tmp.open('rb') as stream:
            os.fsync(stream.fileno())
        result = verify(tmp)
        if replace:
            os.replace(tmp, archive)
        else:
            # Atomic no-clobber publication on the same filesystem.
            os.link(tmp, archive)
            tmp.unlink()
        result['archive'] = str(archive)
        return result
    finally:
        tmp.unlink(missing_ok=True)


def unpack(archive: Path, destination: Path, *, max_bytes: int = MAX_BYTES) -> dict:
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(str(destination))
    temporary = None
    try:
        with zipfile.ZipFile(archive) as z:
            manifest = _check_open(z, max_bytes)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=destination.name + '.', suffix='.partial', dir=destination.parent))
            for row in manifest['files']:
                out = temporary.joinpath(*PurePosixPath(row['path']).parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(manifest['root'] + '/' + row['path']) as src, out.open('xb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                if sha256_file(out) != row['sha256']:
                    raise ValueError('integrity changed during extraction')
                out.chmod(row['mode'])
            (temporary / MANIFEST).write_bytes(z.read(manifest['root'] + '/' + MANIFEST))
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(str(destination))
            temporary.rename(destination)
            temporary = None
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError('invalid ZIP or integrity failure') from exc
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
    return {'destination': str(destination), 'files': len(manifest['files']), 'status': 'restored'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('pack'); p.add_argument('--source', type=Path, default=Path('.'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--replace', action='store_true')
    v = sub.add_parser('verify'); v.add_argument('archive', type=Path)
    u = sub.add_parser('unpack'); u.add_argument('archive', type=Path); u.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'pack': result = pack(args.source, args.output, replace=args.replace)
        elif args.action == 'verify': result = verify(args.archive)
        else: result = unpack(args.archive, args.destination)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
