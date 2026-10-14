"""Check a WiX-decompiled MSI against the build payload, without installing it."""
import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--decompiled', type=Path, required=True)
parser.add_argument('--payload', type=Path, required=True)
parser.add_argument('--restore', type=Path, required=True)
args = parser.parse_args()
ns = {'w': 'http://wixtoolset.org/schemas/v4/wxs'}
expected = ET.parse(args.manifest).getroot()
actual = ET.parse(args.decompiled).getroot()
package = actual.find('w:Package', ns)
assert package.attrib['Scope'] == 'perUser'
assert package.attrib['Version'] == '1.0.0'
expected_files = {node.attrib['Id']: Path(node.attrib['Source']) for node in expected.findall('.//w:File', ns)}
actual_files = {node.attrib['Id']: Path(node.attrib['Source']) for node in actual.findall('.//w:File', ns)}
assert expected_files.keys() == actual_files.keys()
payload = args.payload.resolve()
restore = args.restore.resolve()
restore.mkdir(parents=True, exist_ok=True)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').digest()

for ident, source in expected_files.items():
    extracted = actual_files[ident]
    if extracted.parts[0] == 'SourceDir':
        extracted = args.decompiled.parent / 'extracted' / Path(*extracted.parts[1:])
    assert digest(source) == digest(extracted), source
    relative = source.resolve().relative_to(payload)
    target = restore / relative
    assert target.resolve().is_relative_to(restore)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(extracted, target)
assert {n.attrib['Id'] for n in actual.findall('.//w:Shortcut', ns)} >= {'StartShortcut', 'DesktopLink'}
print(json.dumps({'msi_files_verified': len(expected_files), 'version': package.attrib['Version'], 'scope': package.attrib['Scope'], 'restored': str(restore)}))
