"""Accept recorded outcomes for the two fixed native protocols, without execution."""
from .release_checks import SHARED_CHECKS

EXIT_CODES = {'accepted': 0, 'behavior_failed': 1, 'invalid_result': 2, 'run_incomplete': 3}
SCOPE = 'saved native result acceptance; no oracle rerun or wire verification'
TASKS = ('visible-policy-a', 'visible-policy-b')
CHECK_NAMES = set(SHARED_CHECKS) | {'dependency_policy'}
INTEGRITY = ('app_server_reaped', 'bridges_cleaned', 'candidate_cleaned', 'config_unchanged',
             'runner_unchanged', 'tasks_unchanged')
SCENARIOS = {
    'fixed-policy': ('codex-native-compaction-smoke-v1', 2, ('A', 'B'), TASKS),
    'policy-revision': ('codex-native-policy-revision-v1', 4, ('A-to-B', 'B-to-A'), TASKS[::-1]),
}
ARM_ORDERS = (('control', 'native-compact'), ('native-compact', 'control'))


class InvalidResult(Exception):
    def __init__(self, code, location):
        self.reason = {'code': code, **location}


def require(condition, code, **location):
    if not condition:
        raise InvalidResult(code, location)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate_json_key')
        value[key] = item
    return value


def result(verdict, scenario, observed, reasons):
    return {'verdict': verdict, 'scenario': scenario, 'scope': SCOPE,
            'expected_candidates': 4, 'observed_candidates': observed, 'reasons': reasons}


def check_phase(phase, kind, location, incomplete):
    # Failed setup produces {} privately and null fields in public projection.
    if phase is None:
        incomplete.append({'code': 'phase_missing', **location})
        return
    require(type(phase) is dict, 'phase_type', **location)
    for key in ('kind', 'status', 'terminal', 'cancellation'):
        require(phase.get(key) is None or type(phase[key]) is str, 'phase_field_type', **location)
    calls = phase.get('tool_calls')
    require(calls is None or (type(calls) is int and calls >= 0), 'tool_count_type', **location)
    if phase.get('kind') is None:
        require(all(phase.get(k) is None for k in ('status', 'terminal', 'cancellation', 'tool_calls')),
                'phase_kind_missing', **location)
        incomplete.append({'code': 'phase_missing', **location})
    else:
        require(phase['kind'] == kind, 'phase_kind', **location)
        if (phase.get('status') != 'completed' or phase.get('terminal') != 'completed'
                or phase.get('cancellation') != 'not_requested'):
            incomplete.append({'code': 'phase_not_completed', **location})
        if calls is None or calls > (16 if kind == 'continuation' else 0):
            incomplete.append({'code': 'tool_budget_unconfirmed', **location})
    evidence = phase.get('evidence', [])
    require(type(evidence) is list, 'evidence_type', **location)
    for event in evidence:
        require(type(event) is dict and type(event.get('event')) is str, 'evidence_entry', **location)
        if event['event'] == 'turn_completed':
            require(event.get('status') is None or type(event['status']) is str, 'evidence_status_type', **location)
    compact = any(e['event'] == 'compaction_completed' for e in evidence)
    terminal = any(e['event'] == 'turn_completed' and e.get('status') == 'completed' for e in evidence)
    if kind == 'compact' and not (compact and terminal):
        incomplete.append({'code': 'compact_evidence_missing', **location})
    if kind != 'compact' and compact:
        incomplete.append({'code': 'automatic_compaction', **location})


def check_oracles(value, target, location, incomplete, failures):
    if value is None:
        incomplete.append({'code': 'oracles_missing', **location})
        return False
    require(type(value) is dict and set(value) <= set(TASKS), 'oracle_set', **location)
    outcomes = {}
    for task, verdict in value.items():
        where = {**location, 'oracle': task}
        require(type(verdict) is dict and type(verdict.get('status')) is str, 'oracle_shape', **where)
        checks = verdict.get('checks')
        require(type(checks) is list, 'oracle_checks_type', **where)
        names = []
        for check in checks:
            require(type(check) is dict and type(check.get('name')) is str, 'check_shape', **where)
            name = check['name']
            require(name in CHECK_NAMES and name not in names, 'check_names', **where)
            names.append(name)
            require(type(check.get('passed')) is bool, 'check_pass_type', **where, check=name)
            if 'error' in check:
                require(type(check['error']) is str and bool(check['error']) and not check['passed'],
                        'check_error_shape', **where, check=name)
        require(set(names) == CHECK_NAMES, 'check_names', **where)
        if verdict['status'] != 'completed':
            incomplete.append({'code': 'oracle_not_completed', **where})
        outcomes[task] = {c['name']: c['passed'] for c in checks}
    if set(outcomes) != set(TASKS):
        incomplete.append({'code': 'oracles_missing', **location})
        return False
    policies = {task: checks['dependency_policy'] for task, checks in outcomes.items()}
    require(not all(policies.values()), 'both_policies_pass', **location)
    for task, checks in outcomes.items():
        for name in SHARED_CHECKS:
            if not checks[name]:
                failures.append({'code': 'shared_rule_failure', **location, 'oracle': task, 'check': name})
    if not policies[target]:
        other = next(task for task in TASKS if task != target)
        failures.append({'code': 'old_or_opposite_policy' if policies[other] else 'neither_policy',
                         **location, 'oracle': target, 'check': 'dependency_policy'})
    return all(v['status'] == 'completed' for v in value.values())


def accept_result(report, scenario):
    """Use only common public/private fields; ignore identities and summaries."""
    incomplete, failures, observed = [], [], 0
    try:
        require(scenario in SCENARIOS, 'unsupported_scenario')
        protocol, seeds, cases, targets = SCENARIOS[scenario]
        revision = scenario == 'policy-revision'
        require(type(report) is dict, 'report_type')
        require(report.get('status') in ('completed', 'running', 'failed'), 'run_status')
        plan = report.get('plan')
        require(type(plan) is dict and plan.get('protocol') == protocol, 'unsupported_plan')
        for key, expected in (('seeds', seeds), ('compactions', 2), ('continuations', 4)):
            require(type(plan.get(key)) is int and plan[key] == expected, 'plan_counts')
        planned = plan.get('pairs')
        require(type(planned) is list and len(planned) == 2, 'plan_pairs')
        for i, pair in enumerate(planned):
            require(type(pair) is dict and pair.get('task') == targets[i]
                    and pair.get('arms') == list(ARM_ORDERS[i]), 'plan_pair', case=cases[i])
            if revision:
                require(pair.get('case_id') == cases[i] and pair.get('initial_task') == TASKS[i],
                        'plan_direction', case=cases[i])
        pairs = report.get('pairs')
        require(type(pairs) is list and len(pairs) <= 2, 'result_pairs')
        if len(pairs) != 2 or report['status'] != 'completed':
            incomplete.append({'code': 'run_not_completed'})
        integrity = report.get('checks')
        require(type(integrity) is dict, 'integrity_type')
        for key in INTEGRITY + (('fixture_unchanged',) if revision else ()):
            require(key not in integrity or type(integrity[key]) is bool, 'integrity_field_type')
            if integrity.get(key) is not True:
                incomplete.append({'code': 'integrity_unconfirmed', 'check': key})
        for i, pair in enumerate(pairs):
            where = {'case': cases[i]}
            require(type(pair) is dict and pair.get('task') == targets[i], 'pair_identity', **where)
            if revision:
                require(pair.get('case_id') == cases[i] and pair.get('initial_task') == TASKS[i],
                        'pair_direction', **where)
            check_phase(pair.get('seed'), 'seed', {**where, 'phase': 'seed'}, incomplete)
            if revision:
                check_phase(pair.get('revision'), 'seed', {**where, 'phase': 'revision'}, incomplete)
            else:
                require('revision' not in pair, 'unexpected_revision', **where)
            arms = pair.get('arms')
            require(type(arms) is list and len(arms) <= 2, 'arms_type', **where)
            if len(arms) != 2:
                incomplete.append({'code': 'arms_missing', **where})
            for j, arm in enumerate(arms):
                arm_name = ARM_ORDERS[i][j]
                location = {**where, 'arm': arm_name}
                require(type(arm) is dict and arm.get('arm') == arm_name, 'arm_identity', **location)
                kinds = ('continuation',) if arm_name == 'control' else ('compact', 'continuation')
                phases = arm.get('phases')
                require(type(phases) is list and len(phases) <= len(kinds), 'phases_type', **location)
                if len(phases) != len(kinds):
                    incomplete.append({'code': 'phases_missing', **location})
                for phase, kind in zip(phases, kinds):
                    check_phase(phase, kind, {**location, 'phase': kind}, incomplete)
                observed += check_oracles(arm.get('cross_verification'), targets[i], location, incomplete, failures)
        verdict = 'run_incomplete' if incomplete else 'behavior_failed' if failures else 'accepted'
        return result(verdict, scenario, observed, incomplete + failures)
    except InvalidResult as error:
        return result('invalid_result', scenario, observed, [error.reason])
