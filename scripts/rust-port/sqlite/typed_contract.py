"""Approved SQLite language differences; never waive an unclassified cause."""
import json

CLOSED = 'closed_db: rusqlite close consumes Connection; no safe closed handle can be passed to migrate'


def apply(go, rust, verdict):
    """Keep raw differences, but gate the explicitly approved phase/cause contract."""
    g = {case['id']: case for case in go['cases']}
    r = {case['id']: case for case in rust['cases']}
    checks = []
    for gkey, rkey, phase, prefix in [
        ('missing_directory', 'directory', 'open', 'failed to open sqlite database:'),
        ('parent_file', 'parent_file', 'directory', 'failed to create database directory:'),
    ]:
        checks.append((f'SQL-001/open_errors/{gkey}',
                       g['SQL-001']['state']['open_errors'][gkey], prefix,
                       g['SQL-001']['state'].get('open_causes', {}).get(gkey),
                       r['SQL-001']['state']['open_errors'][rkey], phase))
    for cid, name, phase, prefix in [
        ('SQL-005', 'exec_failure', 'execute', 'failed to execute migration 001_partial:'),
        ('SQL-005', 'insert_failure', 'record', 'failed to record migration 001_test:'),
        ('SQL-006', 'missing_directory', 'read_directory', 'failed to read migrations directory:'),
        ('SQL-006', 'version_query', 'check_state', 'failed to check migration state for 001_test:'),
        ('SQL-006', 'read_file', 'read_migration', 'failed to read migration 001_test.sql:'),
    ]:
        negative = next(n for n in g[cid]['negative'] if n['name'] == name)
        checks.append((f'{cid}/errors/{name}', negative['error'], prefix,
                       negative.get('cause'), r[cid].get('errors', {}).get(name, {}), phase))
    gc, rc = g['SQL-002']['state']['contention'], r['SQL-002']['state']['contention']
    checks.append(('SQL-002/contention/writer_error', gc['writer_error'], 'database is locked',
                   gc.get('writer_cause'), {'kind': 'writer', 'error': rc['writer_error'],
                                           'cause': rc.get('writer_cause')}, 'writer'))
    allowed = set()
    failures = []
    for path, text, prefix, cause, observed, phase in checks:
        valid_cause = isinstance(cause, dict) and (
            cause.get('type') == 'sqlite' and type(cause.get('code')) is int and cause['code'] in (1, 5, 14)
            or cause.get('type') == 'io' and cause.get('kind') in ('NotFound', 'NotADirectory'))
        matches = (valid_cause and text.startswith(prefix) and observed.get('kind') == phase
                   and bool(observed.get('error'))
                   and json.dumps(cause, sort_keys=True) == json.dumps(observed.get('cause'), sort_keys=True))
        if matches:
            allowed.add(path)
        else:
            failures.append({'path': path + '/typed_contract', 'go': cause, 'rust': observed})
    closed = next(n for n in g['SQL-006']['negative'] if n['name'] == 'closed_db')
    if (closed['error'] == 'failed to create schema_migrations table: sql: database is closed'
            and r['SQL-006'].get('unsupported') == [CLOSED]
            and 'closed_db' not in r['SQL-006'].get('errors', {})):
        allowed.add('SQL-006/errors/closed_db')
    else:
        failures.append({'path': 'SQL-006/errors/closed_db/lifecycle_contract'})
    accepted = [d for d in verdict['differences'] if d['path'] in allowed]
    remaining = [d for d in verdict['differences'] if d['path'] not in allowed] + failures
    return {**verdict, 'status': 'passed' if not remaining else 'partial',
            'comparison_contract': 'approved-typed-errors-and-consuming-close',
            'accepted_differences': accepted, 'differences': remaining}
