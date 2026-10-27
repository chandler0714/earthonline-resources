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
    paths = sorted(Path(path).glob('*.json'))
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', type=Path, default=ROOT / 'resources')
    errors = validate_directory(parser.parse_args().directory)
    for error in errors:
        print(error)
    print(f'{len(errors)} validation errors; scientific review remains separate')
    raise SystemExit(bool(errors))
