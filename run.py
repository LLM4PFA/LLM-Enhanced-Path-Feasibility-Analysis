"""Validate experiment inputs and launch the original analysis; no run logs are saved."""
import argparse
import ast
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'llm4pfa/configs/linux-codeql-npd.json'
DEPENDENCIES = ['openai', 'anthropic', 'z3', 'clang', 'lizard', 'tqdm', 'requests']
ENV_INPUTS = {'input': 'PFA_INPUT', 'context': 'PFA_CONTEXT',
              'constraints': 'PFA_CONSTRAINTS', 'dereferences': 'PFA_DEREFERENCE_CACHE'}


def resolve(value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment():
    env = {}
    path = ROOT / '.env'
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.removeprefix('export ').partition('=')
            if not sep or not re.fullmatch(r'[A-Z_][A-Z_0-9]*', key.strip()):
                raise ValueError(f'.env line {number}: expected KEY=VALUE')
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            env[key.strip()] = value
    # An explicitly exported value takes precedence over .env.
    env.update(os.environ)
    return env


def normalized(value):
    return re.sub(r'\s+', '', value)


def validate_data(data, expected):
    """Validate the actual original consumer contract, without inventing records."""
    errors = []
    rows = data.get('input')
    if rows is not None:
        if not isinstance(rows, list) or not rows:
            errors.append('input: expected a nonempty list')
            rows = None
        elif expected and len(rows) != expected:
            errors.append(f'input: expected {expected} records, got {len(rows)}')
    for key in ['context', 'constraints']:
        value = data.get(key)
        if value is not None and (not isinstance(value, list) or (rows is not None and len(value) != len(rows))):
            errors.append(f'{key}: expected a list with the same length as input')
    if rows:
        for i, row in enumerate(rows):
            try:
                var = row['var_name']; code = row['function_code']
                location = row['location']; sink = location['context']['snippet']['text']
                assert all(isinstance(s, str) and s for s in [var, code, sink, location['file_path']])
                assert isinstance(location['region']['startLine'], int)
            except (KeyError, TypeError, AssertionError):
                errors.append(f'input[{i}]: missing/invalid variable, code or location')
                continue
            ctx = data.get('context')
            if isinstance(ctx, list) and i < len(ctx):
                try:
                    c = ctx[i]
                    assert isinstance(c['function_call'], list) and c['function_call']
                    assert all(isinstance(s, str) and s for s in c['function_call'])
                    assert c['prt'] == var
                    assert normalized(c['sink']) == normalized(sink)
                    assert normalized(c['function_call'][0]) == normalized(code)
                except (KeyError, TypeError, AssertionError):
                    errors.append(f'context[{i}]: invalid chain or identity mismatch')
            con = data.get('constraints')
            if isinstance(con, list) and i < len(con):
                try:
                    c = con[i]
                    assert isinstance(c['target_conditions'], list)
                    assert isinstance(c['early_jump_constraints'], list)
                    for field, target in [('var_name', var), ('loc_text', sink), ('code_snippet', code)]:
                        if field in c:
                            assert normalized(c[field]) == normalized(target)
                except (KeyError, TypeError, AssertionError):
                    errors.append(f'constraints[{i}]: invalid constraints or identity mismatch')
    deref = data.get('dereferences')
    if deref is not None:
        if not isinstance(deref, dict) or not deref:
            errors.append('dereferences: expected a nonempty object; an empty cache is not a substitute')
        else:
            for key, item in deref.items():
                try:
                    assert '@' in key and all(key.split('@', 1))
                    assert isinstance(item, dict)
                    assert isinstance(item['location_line'], list) and item['location_line']
                    assert all(isinstance(s, str) and s for s in item['location_line'])
                    assert int(item['line_number']) > 0
                    assert isinstance(item['file_uri'], str) and item['file_uri']
                except (KeyError, TypeError, ValueError, AssertionError):
                    errors.append(f'dereferences[{key}]: invalid location record')
    return errors


def check(config, env, allow_missing_dereferences=False):
    errors = []; warnings = []; data = {}; files = {}
    for key in ENV_INPUTS:
        path = resolve(config['inputs'][key])
        files[key] = {'path': str(path), 'exists': path.is_file()}
        if not path.is_file():
            if key == 'dereferences' and allow_missing_dereferences:
                files[key]['fallback'] = 'explicit-empty-cache'
                warnings.append('Dereference index unavailable: starting an empty per-run cache at user request; original cache misses may return True.')
                continue
            errors.append(f'missing {key}: {path}')
            continue
        try:
            data[key] = json.loads(path.read_text())
            files[key].update(sha256=sha(path), records=len(data[key]))
        except (OSError, ValueError, TypeError):
            errors.append(f'invalid JSON container: {key}')
    errors.extend(validate_data(data, config.get('expected_records')))
    module = ROOT / 'llm4pfa/llm/tool_schema.py'
    if not module.is_file():
        errors.append(f'missing original module: {module}')
    else:
        try:
            tree = ast.parse(module.read_text())
            names = {n.id for stmt in tree.body if isinstance(stmt, ast.Assign)
                     for target in stmt.targets for n in ast.walk(target) if isinstance(n, ast.Name)}
            if 'tools' not in names:
                errors.append('tool_schema.py: top-level tools assignment not found')
        except (SyntaxError, OSError):
            errors.append('tool_schema.py: invalid Python source')
    source = resolve(env.get('PFA_SOURCE_ROOT') or config['source_root'])
    if not source.is_dir():
        errors.append(f'missing source directory: {source}')
    else:
        makefile = source / 'Makefile'
        text = makefile.read_text(errors='replace') if makefile.is_file() else ''
        version = []
        for key in ['VERSION', 'PATCHLEVEL', 'SUBLEVEL']:
            m = re.search(r'^' + key + r'\s*=\s*(\d+)\s*$', text, re.M)
            version.append(m.group(1) if m else '?')
        if '.'.join(version) != config['source_version']:
            errors.append(f'source version: expected {config["source_version"]}, got {".".join(version)}')
        for row in data.get('input', []) if isinstance(data.get('input'), list) else []:
            try:
                raw = Path(row['location']['file_path'])
                target = (source / raw).resolve()
                if raw.is_absolute() or not target.is_relative_to(source.resolve()) or not target.is_file():
                    errors.append(f'input source file unavailable under source_root: {raw}')
            except (KeyError, TypeError):
                pass  # The data validator reports this row.
    for field, evidence in config.get('evidence', {}).items():
        if evidence != 'recovered-original':
            warnings.append(f'{field}: provenance={evidence}; availability does not authenticate the experiment version')
    warnings.append('Schema checks do not prove dereference-cache coverage or exact paper-result reproducibility.')
    if config.get('model_factory') != 'gpt':
        errors.append('This launcher currently configures the recovered GPT adapter only.')
    for dependency in DEPENDENCIES:
        if importlib.util.find_spec(dependency) is None:
            errors.append(f'missing dependency: {dependency}')
    if not env.get('OPENAI_API_KEY', '').strip():
        errors.append('OPENAI_API_KEY is empty')
    if not env.get('OPENAI_BASE_URL', '').strip() or not env.get('OPENAI_MODEL', '').strip():
        errors.append('set OPENAI_BASE_URL and OPENAI_MODEL explicitly in .env or environment')
    return {'experiment': config['id'], 'ready': not errors, 'api_called': False,
            'source_root': str(source), 'files': files,
            'errors': sorted(set(errors)), 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'run'])
    parser.add_argument('--config', default=str(DEFAULT))
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end', type=int)
    parser.add_argument('--output', help='New output directory; defaults to output/<timestamp>')
    parser.add_argument('--allow-missing-dereferences', action='store_true')
    args = parser.parse_args()
    try:
        config = json.loads(resolve(args.config).read_text())
        env = environment()
        report = check(config, env, args.allow_missing_dereferences)
        print('Ready:', report['ready'])
        for error in report['errors']:
            print('ERROR:', error)
        for warning in report['warnings']:
            print('NOTE:', warning)
        if not report['ready']:
            return 2
        if args.command == 'check':
            return 0
        start = args.start
        end = args.end if args.end is not None else start + 1
        count = report['files']['input']['records']
        if not 0 <= start < end <= count:
            raise ValueError(f'expected 0 <= start < end <= {count}')
        directory = resolve(args.output) if args.output else ROOT/'output'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        directory.mkdir(parents=True, exist_ok=False)
        runtime = dict(env)
        for key, variable in ENV_INPUTS.items():
            runtime[variable] = report['files'][key]['path']
        if report['files']['dereferences'].get('fallback') == 'explicit-empty-cache':
            cache = directory/'dereferences.json'
            cache.write_text('{}\n')
            runtime['PFA_DEREFERENCE_CACHE'] = str(cache)
        runtime.update(PFA_SOURCE_ROOT=report['source_root'], PFA_START=str(start), PFA_END=str(end),
                       PFA_MODEL_FACTORY=config['model_factory'], PFA_OUTPUT=str(directory/'results.json'),
                       PFA_FUNCTION_CACHE=str(directory/'function-cache.json'),
                       PFA_MEMORY_CACHE=str(directory/'memory-cache.json'), PYTHONUNBUFFERED='1',
                       PYTHONPATH=str(ROOT))
        print('Results:', directory/'results.json', flush=True)
        completed = subprocess.run([sys.executable, '-m', 'llm4pfa.analysis.pipeline'],
                                   cwd=ROOT, env=runtime)
        if completed.returncode:
            return completed.returncode
        path = directory/'results.json'
        rows = json.loads(path.read_text()) if path.is_file() else []
        valid = isinstance(rows, list) and len(rows) == end-start and all(
            isinstance(row, dict) and type(row.get('result')) is bool for row in rows)
        print('Analysis finished.' if valid else 'Some records failed; inspect results.json.')
        return 0 if valid else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Configuration/run error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
