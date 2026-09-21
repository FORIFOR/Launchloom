import json


def test_readiness_command_loads_literal_env_without_exposing_secrets(tmp_path):
    import os
    import subprocess
    import sys
    (tmp_path / '.env').write_text('ENABLE_CREATIVE_AI=1\nLLM_BASE_URL=http://127.0.0.1:1234/v1\nLLM_MODEL=test-local\nLLM_API_KEY=PRIVATE-TEST-KEY\n')
    env = {k:v for k,v in os.environ.items() if k not in {'ENABLE_CREATIVE_AI','LLM_BASE_URL','LLM_MODEL','LLM_API_KEY'}}
    result = subprocess.run([sys.executable,'-m','launchloom.creative_readiness'], cwd=tmp_path, env=env,
                            capture_output=True, text=True, check=True, timeout=20)
    report = json.loads(result.stdout)
    assert report['integrations']['creative_ai']['configured'] is True
    assert all(not x['live_verified'] for x in report['integrations'].values())
    assert 'PRIVATE-TEST-KEY' not in result.stdout + result.stderr
