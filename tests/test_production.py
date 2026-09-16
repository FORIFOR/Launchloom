import copy
import io
import json
import zipfile
import pytest
from launchloom.production import initial_plan, validate_plan, revision, build_bundle, after_effects_script


def example():
    return initial_plan({'name': 'Sample', 'tagline': '伝える', 'features': [
        {'title': 'Approved feature', 'approved': True, 'evidence': 'PRIVATE-EVIDENCE'},
        {'title': 'UNAPPROVED-FEATURE', 'approved': False}]})


def test_default_does_not_export_private_evidence_or_unapproved_features():
    plan = example()
    assert plan['scenes'][1]['title'] == 'Approved feature'
    with zipfile.ZipFile(io.BytesIO(build_bundle(plan))) as z:
        data = '\n'.join(z.read(n).decode() for n in z.namelist())
    assert 'PRIVATE-EVIDENCE' not in data
    assert 'UNAPPROVED-FEATURE' not in data


@pytest.mark.parametrize('seconds', [float('nan'), float('inf'), -1, 0, 31, True, '4'])
def test_invalid_duration(seconds):
    plan = example(); plan['scenes'][0]['seconds'] = seconds
    with pytest.raises(ValueError): validate_plan(plan)


@pytest.mark.parametrize('sid', ['../secrets', '/tmp/video', 'x.mp4', 'a/b', 'a\\b', 'x\n'])
def test_invalid_ids(sid):
    plan = example(); plan['scenes'][0]['id'] = sid
    # Leading/trailing whitespace is normalized. Newlines within ids are rejected.
    if sid == 'x\n':
        assert validate_plan(plan)['scenes'][0]['id'] == 'x'
    else:
        with pytest.raises(ValueError): validate_plan(plan)


def test_unknown_keys_and_duplicate_ids():
    plan = example(); plan['api_key'] = 'SECRET'
    with pytest.raises(ValueError): validate_plan(plan)
    plan = example(); plan['scenes'][1]['id'] = 'opening'
    with pytest.raises(ValueError): validate_plan(plan)


@pytest.mark.parametrize('field,value', [('fps', True), ('fps', 60), ('aspect_ratio', '4:3'), ('schema_version', True), ('scenes', [])])
def test_invalid_plan_fields(field, value):
    plan = example(); plan[field] = value
    with pytest.raises(ValueError): validate_plan(plan)


def test_total_duration_limit():
    plan = example(); scene = plan['scenes'][0]
    plan['scenes'] = [dict(scene, id=f'scene{i}', seconds=30) for i in range(5)]
    with pytest.raises(ValueError): validate_plan(plan)


def test_revision_changes_and_normalization_is_pure():
    p = example(); before = copy.deepcopy(p)
    assert validate_plan(p) == p and p == before
    r = revision(p); p['scenes'][0]['prompt'] += ' change'
    assert revision(p) != r


def test_bundle_is_valid_and_has_no_completed_assets():
    p = example()
    with zipfile.ZipFile(io.BytesIO(build_bundle(p))) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == {'production.json', 'README.md', 'AGENT_TASK.md', 'seedance-prompts.md', 'build.jsx', 'assets/README.txt'}
        assert json.loads(z.read('production.json')) == p
        assert 'not API requests' in z.read('seedance-prompts.md').decode()
        assert 'NOT a completed video' in z.read('README.md').decode()


def test_jsx_escapes_untrusted_data_and_refuses_overwrite():
    p = example(); p['scenes'][0]['title'] = '"; system.callSystem("bad"); //\u2028'
    script = after_effects_script(p)
    literal = script.split('var plan = ', 1)[1].split(';\n    var base', 1)[0]
    assert json.loads(literal)['scenes'][0]['title'] == p['scenes'][0]['title'].strip()
    assert 'projectFile.exists' in script
    assert 'app.project.numItems > 0' in script
    assert 'nothing was rendered' in script
    assert 'renderQueue.render' not in script
