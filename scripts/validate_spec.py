# Copy this into scripts/validate_spec.py in M0; for now standalone baseline validator.
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
cat=json.loads((ROOT/'catalogs/asset_catalog.json').read_text('utf-8'))
legacy=json.loads((ROOT/'catalogs/legacy_41_mapping.json').read_text('utf-8'))['records']
assert len(legacy)==41 and len(set(x['legacy_id'] for x in legacy))==41
assert len(cat['new_asset_templates'])==14
assert [x['id'] for x in cat['new_asset_templates']]==[f'NEW-{i:02d}' for i in range(1,15)]
assert [x['id'] for x in cat['application_kits']]==[f'APP-{i:02d}' for i in range(1,11)]
for d in (ROOT/'schemas').glob('*.json'):json.loads(d.read_text('utf-8'))
for id in [x['id'] for x in cat['new_asset_templates']]:
  assert f'### {id}' in (ROOT/'prompts/new-assets.md').read_text('utf-8'),id
for id in [x['id'] for x in cat['application_kits']]:
  assert f'### {id}' in (ROOT/'prompts/application-kits.md').read_text('utf-8'),id
for name in ['BASE_VIEW','BASE_DETAIL','BASE_EXPRESSION','BASE_POSE','BASE_STRUCTURE','BASE_OUTFIT','BASE_PROFILE']:
  assert f'### {name}' in (ROOT/'prompts/common-and-legacy.md').read_text('utf-8')
print('OK: 41 legacy mappings + 14 new + 10 kits + schemas and prompt families.')

# Style library v1.2 validation (planned examples do not count as generated)
styles=json.loads((ROOT/'styles/catalog.json').read_text('utf-8'))
assert len(styles['groups'])==8
assert len(styles['styles'])==48
assert [x['style_id'] for x in styles['styles']]==[f'STYLE-{i:03d}' for i in range(1,49)]
assert {x['group_id'] for x in styles['styles']}=={x['group_id'] for x in styles['groups']}
for x in styles['styles']:
  assert x['display_name_zh'] and x['description_zh'] and x['prompt_fragment_en'] and x['supported_subjects']
  assert len(x['prompt_fragment_en'])>35
  assert set(x['supported_subjects']) <= {'anime_human','animal','anthropomorphic_object','fantasy_creature'}
manifest=json.loads((ROOT/'styles/preview_manifest.json').read_text('utf-8'))
assert manifest['minimum_required_for_v1']==48
assert {x['style_id'] for x in manifest['items']}=={x['style_id'] for x in styles['styles']}
assert all(x['status']=='planned' and x['actual_file'] is None for x in manifest['items'])
print('OK: 48 styles across 8 groups + preview request manifest. No sample images claimed generated.')

# Validate style value enums and seed migration aliases
taxonomy=json.loads((ROOT/'styles/taxonomy.json').read_text('utf-8'))['dimensions']
for s in styles['styles']:
    for key in ('medium','tradition','proportions','material','linework','detail'):
        assert s[key] in taxonomy[key],(s['style_id'], key, s[key])
    assert set(s['mood']) <= set(taxonomy['mood'])
    assert s['preview_prototype_preference'] in s['supported_subjects']
assert len({x['preview_id'] for x in manifest['items']})==len(manifest['items'])
for x in manifest['items']:
    assert x['prompt_sha256'] == __import__('hashlib').sha256(x['prompt'].encode('utf-8')).hexdigest()
alias=json.loads((ROOT/'styles/legacy_style_aliases.json').read_text('utf-8'))['aliases']
assert set(alias.values()) <= {s['style_id'] for s in styles['styles']}
print('OK: style taxonomy values, preview prompt hashes and pre-release alias mapping.')
