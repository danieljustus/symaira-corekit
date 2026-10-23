#!/usr/bin/env python3
"""Render an approved A3 foreground on the shared neutral icon backgrounds.

Requires macOS Icon Composer and Pillow. Does not draw or recolor the S/signet.
The output directory is a review handoff, never a release or installed app.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RENDERER = Path('/Applications/Icon Composer.app/Contents/Executables/ictool')
MODES = ('Default', 'Dark', 'TintedDark')
PLATFORMS = ('macOS', 'iOS')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def color(spec: str, role: str) -> str:
    match = re.search(r'^  ' + re.escape(role) + r': "(#[0-9A-Fa-f]{6})"$', spec, re.M)
    if not match:
        raise ValueError(f'Missing canonical color role: {role}')
    return match[1]


def native_color(value: str) -> str:
    return 'srgb:' + ','.join(f'{int(value[i:i + 2], 16) / 255:.8f}' for i in (1, 3, 5)) + ',1'


def render(source: Path, output: Path, design: Path, renderer: Path) -> None:
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Source package and output must be separate, non-nested paths')
    original = json.loads((source / 'icon.json').read_text())
    if len(original.get('groups', [])) != 2:
        raise ValueError('Expected the approved two-group A3 composition')
    assets = {layer['image-name'] for group in original['groups'] for layer in group['layers']}
    if assets != {'S.png', 'signet.png'}:
        raise ValueError('Unexpected A3 layer assets')
    if any(not (source / 'Assets' / name).is_file() for name in assets):
        raise ValueError('Missing source artwork')
    spec = design.read_text()
    light, dark = color(spec, 'canvas'), color(spec, 'canvas-dark')
    document = {key: value for key, value in original.items() if key not in ('fill', 'fill-specializations')}
    document['fill-specializations'] = [
        {'value': {'solid': native_color(light)}},
        {'appearance': 'dark', 'value': {'solid': native_color(dark)}},
        {'appearance': 'tinted', 'value': 'automatic'},
    ]
    package, exports, iconset = output / 'AppIcon.icon', output / 'exports', output / 'AppIcon.iconset'
    for directory in (package / 'Assets', exports, iconset):
        directory.mkdir(parents=True, exist_ok=True)
    for name in sorted(assets):
        shutil.copy2(source / 'Assets' / name, package / 'Assets' / name)
    (package / 'icon.json').write_text(json.dumps(document, indent=2) + '\n')
    renders = []
    for platform in PLATFORMS:
        for mode in MODES:
            path = exports / f'{platform}-{mode}.png'
            subprocess.run([str(renderer), str(package), '--export-image', '--output-file', str(path),
                            '--platform', platform, '--rendition', mode,
                            '--width', '1024', '--height', '1024', '--scale', '1'],
                           check=True, timeout=90, capture_output=True)
            with Image.open(path) as image:
                extrema = ImageStat.Stat(image.convert('RGB')).extrema
                if image.size != (1024, 1024) or max(hi - lo for lo, hi in extrema) <= 50:
                    raise ValueError(f'Invalid or blank rendition: {path.name}')
            renders.append({'platform': platform, 'mode': mode, 'path': str(path.relative_to(output)), 'sha256': sha(path)})
    with Image.open(exports / 'macOS-Default.png') as image:
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                suffix = '@2x' if scale == 2 else ''
                image.resize((size * scale, size * scale), Image.Resampling.LANCZOS).save(iconset / f'icon_{size}x{size}{suffix}.png')
    subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(exports / 'AppIcon.icns')], check=True, timeout=30)
    with Image.open(exports / 'iOS-Default.png').convert('RGBA') as image:
        opaque = Image.new('RGBA', image.size, light)
        Image.alpha_composite(opaque, image).convert('RGB').save(exports / 'ios-1024-opaque.png')
    # One executable integrity check: preserve the entire approved foreground and every input byte.
    assert document['groups'] == original['groups']
    assert all(sha(source / 'Assets' / name) == sha(package / 'Assets' / name) for name in assets)
    assert (exports / 'AppIcon.icns').read_bytes().startswith(b'icns')
    manifest = {
        'design': 'Liquid Topography', 'design_sha256': sha(design), 'background_only': True,
        'source_icon_json_sha256': sha(source / 'icon.json'),
        'foreground_assets': {name: sha(source / 'Assets' / name) for name in sorted(assets)},
        'clear_system_appearance': 'not verified by this CLI',
        'tinted_appearance': 'system tint; not the normal brand palette', 'renders': renders,
        'files': {str(path.relative_to(output)): sha(path) for directory in (package, exports, iconset)
                  for path in sorted(directory.rglob('*')) if path.is_file()},
    }
    (output / 'render-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'6 renditions, 10 iconset images, ICNS and opaque iOS export verified in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Approved AppIcon.icon package')
    parser.add_argument('--output', required=True, type=Path, help='Separate review/export directory')
    parser.add_argument('--design', type=Path, default=ROOT / 'design/liquid-topography/DESIGN.md')
    parser.add_argument('--renderer', type=Path, default=DEFAULT_RENDERER)
    arguments = parser.parse_args()
    render(arguments.source, arguments.output, arguments.design, arguments.renderer)
