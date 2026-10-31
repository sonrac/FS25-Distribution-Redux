#!/usr/bin/env python3
"""Static mod checks; no game installation or third-party Python packages needed."""

import argparse
from collections import Counter
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lua', default='lua5.1', help='Lua 5.1 or LuaJIT executable')
    args = parser.parse_args()
    lua = shutil.which(args.lua)
    if lua is None:
        parser.error(f'{args.lua} not found; install Lua 5.1 or pass --lua luajit')
    version = subprocess.run(
        [lua, '-e', 'io.write(_VERSION)'], capture_output=True, text=True, check=True
    ).stdout
    if version != 'Lua 5.1':
        parser.error(f'expected Lua 5.1 compatibility, got {version}')

    errors = []
    lua_files = sorted((ROOT / 'scripts').rglob('*.lua'))
    if not lua_files:
        errors.append('scripts/: no Lua files found')
    # loadfile compiles each file independently, without executing GIANTS API calls.
    for path in lua_files:
        result = subprocess.run(
            [lua, '-', str(path)],
            input='local f,e=loadfile(arg[1]); if not f then '
                  'io.stderr:write(e,"\\n"); os.exit(1) end',
            capture_output=True, text=True,
        )
        if result.returncode:
            errors.append(f'{path.relative_to(ROOT)}: {result.stderr.strip()}')

    xml_files = [ROOT / 'modDesc.xml']
    for directory in ('gui', 'translations'):
        files = sorted((ROOT / directory).rglob('*.xml'))
        if not files:
            errors.append(f'{directory}/: no XML files found')
        xml_files.extend(files)
    trees = {}
    for path in xml_files:
        try:
            trees[path] = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as error:
            errors.append(f'{path.relative_to(ROOT)}: {error}')

    def require_file(value, context):
        if not value or not (ROOT / value).is_file():
            errors.append(f'{context}: missing file {value!r}')

    desc = trees.get(ROOT / 'modDesc.xml')
    if desc is not None:
        if desc.tag != 'modDesc':
            errors.append('modDesc.xml: expected modDesc root')
        if not re.fullmatch(r'\d+(?:\.\d+){3}', desc.findtext('version', '')):
            errors.append('modDesc.xml: version must have four numeric components')
        require_file(desc.findtext('iconFilename'), 'modDesc.xml iconFilename')
        sources = [node.get('filename') for node in desc.findall('./extraSourceFiles/sourceFile')]
        if not sources:
            errors.append('modDesc.xml: no extraSourceFiles')
        for source in sources:
            require_file(source, 'modDesc.xml sourceFile')
        for source, count in Counter(sources).items():
            if count > 1:
                errors.append(f'modDesc.xml: duplicate sourceFile {source!r}')
        localization = desc.find('l10n')
        prefix = localization.get('filenamePrefix') if localization is not None else None
        if prefix:
            require_file(prefix + '_en.xml', 'modDesc.xml l10n')
        else:
            errors.append('modDesc.xml: missing l10n filenamePrefix')

    english = set()
    for path, root in trees.items():
        if path.parent != ROOT / 'translations':
            continue
        if root.tag != 'l10n' or root.find('texts') is None:
            errors.append(f'{path.name}: expected l10n/texts structure')
        names = []
        for node in root.findall('./texts/text'):
            name = node.get('name')
            if not name or node.get('text') is None:
                errors.append(f'{path.name}: translation needs name and text attributes')
            names.append(name)
        for name, count in Counter(names).items():
            if count > 1:
                errors.append(f'{path.name}: duplicate translation {name!r}')
        if path.name == 'translation_en.xml':
            english.update(names)
    if not english:
        errors.append('translations/translation_en.xml: no English translation keys')
    for path in xml_files:
        if path.parent == ROOT / 'gui' and path in trees:
            for node in trees[path].iter():
                for value in node.attrib.values():
                    if value.startswith('$l10n_') and value[6:] not in english:
                        errors.append(f'{path.name}: missing English translation {value[6:]!r}')

    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)
    print(f'Checked {len(lua_files)} Lua files and {len(xml_files)} XML files; '
          f'{len(errors)} error(s).')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
