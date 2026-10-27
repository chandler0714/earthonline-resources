import copy
import unittest
from tools.validate import validate_resource, validate_directory


def sample():
    return {
        'schema_version': '1.0', 'id': 'water', 'name': {'zh': '水', 'en': 'Water'},
        'category': 'substance', 'description': '常见液体',
        'composition': {'formula': 'H2O', 'source_ids': ['nist']},
        'appearance': {'phase': 'liquid', 'description': '无色透明，条件约 20°C、常压'},
        'properties': [], 'formation': '液态水可由冷凝等过程形成',
        'storage': '使用合适的密闭容器，避免污染', 'applications': ['溶剂'],
        'acquisition': [{'kind': 'direct_collection', 'operation': 'collect',
                         'description': '从液态水体收集', 'conditions': ['存在液态水'],
                         'inputs': [], 'equipment': ['容器'], 'source_ids': ['nist']}],
        'sources': [{'id': 'nist', 'url': 'https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185',
                     'title': 'NIST Water', 'locator': 'Formula', 'accessed': '2026-10-27'}],
        'review': {'status': 'unreviewed'},
        'provenance': {'license': 'CC0-1.0', 'contributor': 'Example author'},
    }


class RegistryTests(unittest.TestCase):
    def test_valid_resource_and_mixture(self):
        self.assertEqual(validate_resource(sample()), [])
        d = sample(); d['category'] = 'mixture'
        d['composition'] = {'components': [{'name': '水', 'fraction_min': 0.9, 'fraction_max': 1.0}], 'source_ids': ['nist']}
        self.assertEqual(validate_resource(d), [])

    def test_acquisition_is_required(self):
        d = sample(); del d['acquisition']
        self.assertTrue(validate_resource(d))

    def test_processing_requires_inputs_and_equipment(self):
        d = sample(); a = d['acquisition'][0]; a.update(kind='processing', operation='distill')
        self.assertTrue(validate_resource(d))

    def test_unreferenced_claim_is_rejected(self):
        d = sample(); d['composition']['source_ids'] = ['invented']
        self.assertTrue(validate_resource(d))

    def test_unknown_unit_and_nonfinite_value_rejected(self):
        for value, unit in [(1, 'banana'), (float('nan'), 'kg/m3')]:
            d = sample(); d['properties'] = [{'name': 'density', 'value': value, 'unit': unit, 'conditions': '20°C, 1 atm', 'source_ids': ['nist']}]
            self.assertTrue(validate_resource(d))

    def test_empty_conditions_and_unknown_fields_rejected(self):
        for field in ['conditions', 'description']:
            d = sample(); d['acquisition'][0][field] = [] if field == 'conditions' else ''
            self.assertTrue(validate_resource(d))
        d = sample(); d['script'] = 'run arbitrary code'
        self.assertTrue(validate_resource(d))

    def test_inverted_mixture_range_rejected(self):
        d = sample(); d['category'] = 'mixture'
        d['composition'] = {'components': [{'name': 'water', 'fraction_min': 0.9, 'fraction_max': 0.1}], 'source_ids': ['nist']}
        self.assertTrue(validate_resource(d))

    def test_directory_duplicate_ids_rejected(self):
        import tempfile, json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            for name in ['a', 'b']:
                Path(folder, name + '.json').write_text(json.dumps(sample()))
            self.assertTrue(validate_directory(Path(folder)))


if __name__ == '__main__':
    unittest.main()
