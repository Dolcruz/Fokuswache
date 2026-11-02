"""Collect runtime notices and publish the corresponding unmodified Qt sources."""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(version):
    licenses = ROOT / 'app/licenses'
    licenses.mkdir(parents=True, exist_ok=True)
    cache = ROOT / 'build/sources'
    cache.mkdir(parents=True, exist_ok=True)
    sources = json.loads((ROOT / 'installer/sources.json').read_text('utf-8'))
    notices = re.compile(r'license|copying|copyright|notice|readme|ftl\.|qt_attribution', re.I)
    for source in sources:
        archive = cache / source['filename']
        if not archive.exists():
            print('Downloading ' + source['filename'], flush=True)
            urllib.request.urlretrieve(source['url'], archive)
        if digest(archive) != source['sha256']:
            raise ValueError('Source archive SHA-256 mismatch: ' + source['filename'])
        with tarfile.open(archive) as bundle:
            for member in bundle:
                path = PurePosixPath(member.name)
                if (not member.isfile() or path.is_absolute() or '..' in path.parts
                        or not notices.search(str(path))):
                    continue
                target = licenses / path
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as stream, target.open('wb') as output:
                    shutil.copyfileobj(stream, output)
    for name in ('psutil', 'pywin32', 'tzdata', 'PySide6-Essentials', 'shiboken6'):
        dist = metadata.distribution(name)
        for file in dist.files or []:
            path = PurePosixPath(str(file))
            if '..' not in path.parts and notices.search(str(path)) and '.dist-info/' in str(path):
                target = licenses / name / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dist.locate_file(file), target)
    shutil.copyfile(Path(sys.base_prefix) / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
    for file in (Path(sys.base_prefix) / 'tcl').glob('*/license.terms'):
        shutil.copyfile(file, licenses / (file.parent.name + '-license.terms'))
    shutil.copyfile(ROOT / 'installer/ThirdPartyNotices.md', licenses / 'ThirdPartyNotices.md')
    shutil.copyfile(ROOT / 'installer/sources.json', licenses / 'sources.json')
    output = ROOT / 'dist' / ('FokusWache-ThirdPartySources-' + version + '.zip')
    output.parent.mkdir(parents=True, exist_ok=True)
    # The source archives are already compressed; preserve them without recompression.
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as bundle:
        for source in sources:
            bundle.write(cache / source['filename'], source['filename'])
        bundle.write(ROOT / 'installer/sources.json', 'sources.json')
        bundle.write(ROOT / 'installer/ThirdPartyNotices.md', 'ThirdPartyNotices.md')
    print('Runtime notices and corresponding sources prepared.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    package(parser.parse_args().version)
