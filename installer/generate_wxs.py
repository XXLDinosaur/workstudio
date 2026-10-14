"""Generate deterministic WiX component IDs for the complete offline payload."""
import argparse
import hashlib
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

NS = 'http://wixtoolset.org/schemas/v4/wxs'
ET.register_namespace('', NS)
ET.register_namespace('ui', 'http://wixtoolset.org/schemas/v4/wxs/ui')
ROOT = Path(__file__).resolve().parents[1]


def add(parent, tag, **attrs):
    return ET.SubElement(parent, '{' + NS + '}' + tag, attrs)


def ident(prefix, path):
    return prefix + hashlib.sha256(str(path).replace('\\', '/').lower().encode()).hexdigest()[:28]


def generate(payload, output, version):
    wix = ET.Element('{' + NS + '}Wix')
    package = add(wix, 'Package', Name='workstudio', Manufacturer='XXLDinosaur', Version=version,
                  UpgradeCode='D9309A10-75DF-4657-A6B4-7DC0134FCE50', Scope='perUser', Language='2052', Codepage='65001')
    add(package, 'MajorUpgrade', DowngradeErrorMessage='已安装更新版本的 workstudio。')
    add(package, 'MediaTemplate', EmbedCab='yes', CompressionLevel='medium')
    add(package, 'Launch', Condition='Installed OR VersionNT64', Message='workstudio 需要 64 位 Windows 系统。')
    add(package, 'Property', Id='ARPPRODUCTICON', Value='AppIcon')
    add(package, 'Property', Id='ARPURLINFOABOUT', Value='https://github.com/XXLDinosaur/workstudio')
    add(package, 'Icon', Id='AppIcon', SourceFile=str(payload / 'workstudio.ico'))
    local = add(package, 'StandardDirectory', Id='LocalAppDataFolder')
    programs = add(local, 'Directory', Id='UserPrograms', Name='Programs')
    install = add(programs, 'Directory', Id='INSTALLFOLDER', Name='workstudio')
    feature = add(package, 'Feature', Id='Complete', Title='workstudio', Level='1')
    directories = {Path('.'): install}
    files = sorted(p for p in payload.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for source in files:
        relative = source.relative_to(payload)
        for folder in reversed(relative.parent.parents):
            if folder != Path('.') and folder not in directories:
                directories[folder] = add(directories[folder.parent], 'Directory', Id=ident('D', folder), Name=folder.name)
        folder = relative.parent
        if folder not in directories:
            directories[folder] = add(directories[folder.parent], 'Directory', Id=ident('D', folder), Name=folder.name)
        cid = ident('C', relative)
        component = add(directories[folder], 'Component', Id=cid, Guid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'workstudio/' + relative.as_posix().lower())), Bitness='always64')
        add(component, 'File', Id='MainExecutable' if relative.as_posix() == 'workstudio.exe' else ident('F', relative), Source=str(source), Name=source.name)
        add(component, 'RegistryValue', Root='HKCU', Key='Software\\workstudio\\Installer\\Files', Name=cid, Type='integer', Value='1', KeyPath='yes')
        add(feature, 'ComponentRef', Id=cid)
    for folder, directory in directories.items():
        cid = ident('Cleanup', folder)
        cleanup = add(directory, 'Component', Id=cid, Guid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'workstudio/cleanup/' + folder.as_posix())))
        add(cleanup, 'RemoveFolder', Id=ident('Remove', folder), On='uninstall')
        add(cleanup, 'RegistryValue', Root='HKCU', Key='Software\\workstudio\\Installer\\Folders', Name=cid, Type='integer', Value='1', KeyPath='yes')
        add(feature, 'ComponentRef', Id=cid)
    menu = add(package, 'StandardDirectory', Id='ProgramMenuFolder')
    folder = add(menu, 'Directory', Id='AppMenuFolder', Name='workstudio')
    shortcuts = add(folder, 'Component', Id='Shortcuts', Guid='57F148E3-0795-4099-B8F3-F010C00EE29F')
    add(shortcuts, 'Shortcut', Id='StartShortcut', Name='workstudio', Target='[INSTALLFOLDER]workstudio.exe', WorkingDirectory='INSTALLFOLDER', Icon='AppIcon')
    add(shortcuts, 'RemoveFolder', Id='RemoveMenu', On='uninstall')
    add(shortcuts, 'RegistryValue', Root='HKCU', Key='Software\\workstudio', Name='InstallDir', Type='string', Value='[INSTALLFOLDER]', KeyPath='yes')
    add(feature, 'ComponentRef', Id='Shortcuts')
    desktop = add(package, 'StandardDirectory', Id='DesktopFolder')
    shortcut = add(desktop, 'Component', Id='DesktopShortcut', Guid='A85119DC-2A46-4A2E-A48F-B08B22DF2D99')
    add(shortcut, 'Shortcut', Id='DesktopLink', Name='workstudio', Target='[INSTALLFOLDER]workstudio.exe', WorkingDirectory='INSTALLFOLDER', Icon='AppIcon')
    add(shortcut, 'RegistryValue', Root='HKCU', Key='Software\\workstudio', Name='DesktopShortcut', Type='integer', Value='1', KeyPath='yes')
    add(feature, 'ComponentRef', Id='DesktopShortcut')
    ET.SubElement(package, '{http://wixtoolset.org/schemas/v4/wxs/ui}WixUI', {'Id': 'WixUI_InstallDir', 'InstallDirectory': 'INSTALLFOLDER'})
    add(package, 'WixVariable', Id='WixUILicenseRtf', Value=str(ROOT / 'installer' / 'license.rtf'))
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(wix)
    ET.ElementTree(wix).write(output, encoding='utf-8', xml_declaration=True)
    print(f'Prepared {len(files)} files for MSI')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', default=(ROOT / 'VERSION').read_text().strip())
    args = parser.parse_args()
    license_text = (ROOT / 'LICENSE').read_text('utf-8').replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}').replace('\n', '\\par\n')
    (ROOT / 'installer' / 'license.rtf').write_text('{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Segoe UI;}}\\f0\\fs18 ' + license_text + '}', 'utf-8')
    generate(args.payload.resolve(), args.output, args.version)
