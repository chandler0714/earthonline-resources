"""Structural checks only; scientific truth and owner release approval are separate."""
import argparse
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schema/resource.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def validate_resource(data):
    errors = [f"{'.'.join(map(str, e.absolute_path))}: {e.message}" for e in VALIDATOR.iter_errors(data)]
    if errors:
        return errors
    sources = {s['id'] for s in data['sources']}
    if len(sources) != len(data['sources']):
        errors.append('Duplicate source ID')

    def walk(value):
        if isinstance(value, float) and not math.isfinite(value):
            errors.append('Non-finite numeric value')
        elif isinstance(value, dict):
            for ref in value.get('source_ids', []):
                if ref not in sources:
                    errors.append(f'Unknown evidence reference: {ref}')
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(data)
    composition = data['composition']
    if data['category'] == 'mixture' and 'components' not in composition:
        errors.append('Mixtures need components, not a single formula')
    components = composition.get('components', [])
    if any(c['fraction_min'] > c['fraction_max'] for c in components):
        errors.append('Inverted composition interval')
    if sum(c['fraction_min'] for c in components) > 1.00000001:
        errors.append('Minimum fractions exceed one')
    expected_units = {'density': 'kg/m3', 'melting_point': 'degC', 'boiling_point': 'degC', 'hardness': 'Mohs'}
    for claim in data['properties']:
        if claim['unit'] != expected_units[claim['name']]:
            errors.append('Property unit mismatch')
    for acquisition in data['acquisition']:
        if acquisition['operation'] in {'distill', 'refine', 'filter', 'extract'} and acquisition['kind'] != 'processing':
            errors.append('Processing operation must declare processing acquisition')
    return errors


def validate_directory(path):
    errors, seen = [], set()
    paths = sorted(Path(path).rglob('*.json'))
    if not paths:
        return ['No resource files found']
    for file in paths:
        try:
            data = json.loads(file.read_text())
            errors.extend(f'{file.name}: {e}' for e in validate_resource(data))
            identifier = data.get('id')
            if identifier in seen:
                errors.append(f'{file.name}: duplicate resource ID {identifier}')
            seen.add(identifier)
        except (ValueError, TypeError, OSError) as error:
            errors.append(f'{file.name}: {error}')
    return errors


def validate_catalog(root=ROOT):
    """Check browse taxonomy and require exactly one index entry per resource."""
    root = Path(root).resolve()
    try:
        ecosystems = json.loads((root / 'catalog/ecosystems.json').read_text())
        index = json.loads((root / 'catalog/resource-index.json').read_text())
    except (OSError, ValueError) as error:
        return [f'Catalog could not be read: {error}']

    errors = []
    if ecosystems.get('schema_version') != 1 or index.get('schema_version') != 1:
        errors.append('Unsupported catalog schema version')
    sources = {source.get('id') for source in ecosystems.get('sources', [])}
    ecosystem_ids = set()
    for item in ecosystems.get('ecosystems', []):
        identifier = item.get('id')
        if identifier in ecosystem_ids:
            errors.append(f'Duplicate ecosystem ID: {identifier}')
        ecosystem_ids.add(identifier)
        if item.get('realm') not in {'terrestrial', 'freshwater', 'marine'}:
            errors.append(f'Unknown ecosystem realm: {identifier}')
        if not item.get('name', {}).get('en') or not item.get('name', {}).get('zh'):
            errors.append(f'Missing ecosystem name: {identifier}')
        if not item.get('source_ids') or any(source not in sources for source in item['source_ids']):
            errors.append(f'Missing ecosystem evidence: {identifier}')

    domain_ids = set()
    for item in index.get('domains', []):
        identifier = item.get('id')
        if identifier in domain_ids:
            errors.append(f'Duplicate domain ID: {identifier}')
        domain_ids.add(identifier)
        if not item.get('name', {}).get('en') or not item.get('name', {}).get('zh'):
            errors.append(f'Missing domain name: {identifier}')

    ids, paths = set(), set()
    resources_root = (root / 'resources').resolve()
    for item in index.get('resources', []):
        identifier, relative = item.get('id'), item.get('path')
        if identifier in ids:
            errors.append(f'Duplicate indexed resource ID: {identifier}')
        ids.add(identifier)
        if relative in paths:
            errors.append(f'Duplicate indexed resource path: {relative}')
        paths.add(relative)
        if not isinstance(relative, str):
            errors.append(f'Invalid resource path: {relative}')
            continue
        path = (root / relative).resolve()
        if not path.is_relative_to(resources_root) or path.suffix != '.json' or not path.is_file():
            errors.append(f'Invalid or missing indexed resource path: {relative}')
            continue
        try:
            actual_id = json.loads(path.read_text()).get('id')
        except (OSError, ValueError) as error:
            errors.append(f'Indexed resource cannot be read: {relative}: {error}')
            continue
        if actual_id != identifier:
            errors.append(f'Indexed resource ID mismatch: {relative}')
        if not item.get('domains') or any(domain not in domain_ids for domain in item['domains']):
            errors.append(f'Unknown or missing domain for: {identifier}')
        if not isinstance(item.get('ecosystems'), list) or any(tag not in ecosystem_ids for tag in item['ecosystems']):
            errors.append(f'Unknown or missing ecosystem list for: {identifier}')

    actual_paths = {path.relative_to(root).as_posix() for path in resources_root.rglob('*.json')}
    for path in sorted(actual_paths - paths):
        errors.append(f'Unindexed resource: {path}')
    for path in sorted(paths - actual_paths):
        errors.append(f'Index points to absent resource: {path}')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', type=Path, default=ROOT / 'resources')
    errors = validate_directory(parser.parse_args().directory) + validate_catalog()
    for error in errors:
        print(error)
    print(f'{len(errors)} validation errors; scientific review remains separate')
    raise SystemExit(bool(errors))
