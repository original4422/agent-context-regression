"""Accept recorded outcomes for the fixed native protocols, without execution."""
from .release_checks import SHARED_CHECKS
from .native_work import INTERMEDIATE, TASK as WORK_TASK

EXIT_CODES = {'accepted': 0, 'behavior_failed': 1, 'invalid_result': 2, 'run_incomplete': 3}
SCOPE = 'saved native result acceptance; no oracle rerun or wire verification'
TASKS = ('visible-policy-a', 'visible-policy-b')
CHECK_NAMES = set(SHARED_CHECKS) | {'dependency_policy'}
INTEGRITY = ('app_server_reaped', 'bridges_cleaned', 'candidate_cleaned', 'config_unchanged',
             'runner_unchanged', 'tasks_unchanged')
POLICY_SCENARIOS = {
    'fixed-policy': ('codex-native-compaction-smoke-v1', 2, ('A', 'B'), TASKS),
    'policy-revision': ('codex-native-policy-revision-v1', 4, ('A-to-B', 'B-to-A'), TASKS[::-1]),
}
SCENARIOS = (*POLICY_SCENARIOS, 'tool-checkpoint')
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
            'expected_candidates': 2 if scenario == 'tool-checkpoint' else 4, 'observed_candidates': observed, 'reasons': reasons}


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
        if calls is None or calls > (16 if kind == 'continuation' else 8 if kind == 'work' else 0):
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


def check_rows(checks, expected, location):
    require(type(checks) is list, 'oracle_checks_type', **location)
    names = []
    for check in checks:
        require(type(check) is dict and type(check.get('name')) is str, 'check_shape', **location)
        name = check['name']
        require(name in expected and name not in names, 'check_names', **location)
        names.append(name)
        require(type(check.get('passed')) is bool, 'check_pass_type', **location, check=name)
        if 'error' in check:
            require(type(check['error']) is str and bool(check['error']) and not check['passed'],
                    'check_error_shape', **location, check=name)
    require(set(names) == expected, 'check_names', **location)
    return {c['name']: c for c in checks}


def check_oracles(value, target, location, incomplete, failures):
    if value is None:
        incomplete.append({'code': 'oracles_missing', **location})
        return False
    require(type(value) is dict and set(value) <= set(TASKS), 'oracle_set', **location)
    outcomes = {}
    for task, verdict in value.items():
        where = {**location, 'oracle': task}
        require(type(verdict) is dict and type(verdict.get('status')) is str, 'oracle_shape', **where)
        checks = check_rows(verdict.get('checks'), CHECK_NAMES, where)
        if verdict['status'] != 'completed':
            incomplete.append({'code': 'oracle_not_completed', **where})
        outcomes[task] = {name: c['passed'] for name, c in checks.items()}
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
        if scenario == 'tool-checkpoint':
            return accept_work(report)
        protocol, seeds, cases, targets = POLICY_SCENARIOS[scenario]
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


def check_work_oracle(value, location, incomplete, failures, prelude=False):
    if value is None:
        incomplete.append({'code': 'oracles_missing', **location})
        return False
    require(type(value) is dict and type(value.get('status')) is str, 'oracle_shape', **location)
    checks = check_rows(value.get('checks'), set(INTERMEDIATE), location)
    if value['status'] != 'completed':
        incomplete.append({'code': 'oracle_not_completed', **location})
    for name, check in checks.items():
        expected = INTERMEDIATE[name] if prelude else True
        if check['passed'] != expected or check.get('error'):
            (incomplete if prelude else failures).append({
                'code': 'work_precondition_failed' if prelude else 'final_check_failed', **location, 'check': name})
    return value['status'] == 'completed'


def check_work_observation(value, work, location, incomplete):
    if value is None:
        incomplete.append({'code': 'work_observation_missing', **location})
        return
    require(type(value) is dict, 'work_observation_type', **location)
    names = value.get('completed_tools')
    require(type(names) is list and all(type(n) is str and n in
            ('list_files', 'read_file', 'write_file', 'check') for n in names), 'work_tools_shape', **location)
    calls = work.get('tool_calls') if work is not None else None
    required = {'read_file', 'write_file', 'check'}
    if (len(names) != calls or not required <= set(names)
            or names.index('read_file') >= names.index('write_file')
            or max(i for i, n in enumerate(names) if n == 'check') <= max(i for i, n in enumerate(names) if n == 'write_file')):
        incomplete.append({'code': 'work_tool_order_unconfirmed', **location})
    checks = check_rows(value.get('check_results'), {'rate_limit', 'not_found'}, location)
    for name, expected in (('rate_limit', False), ('not_found', True)):
        if checks[name]['passed'] != expected or checks[name].get('error'):
            incomplete.append({'code': 'work_public_check_mismatch', **location, 'check': name})


def accept_work(report):
    scenario = 'tool-checkpoint'
    where = {'case': 'retry-work'}
    incomplete, failures, observed = [], [], 0
    try:
        require(type(report) is dict, 'report_type')
        require(report.get('status') in ('completed', 'running', 'failed'), 'run_status')
        plan = report.get('plan')
        require(type(plan) is dict and plan.get('protocol') == 'codex-native-tool-checkpoint-v1', 'unsupported_plan')
        for key, expected in (('work_turns', 1), ('compactions', 1), ('continuations', 2)):
            require(type(plan.get(key)) is int and plan[key] == expected, 'plan_counts')
        planned = plan.get('pairs')
        require(type(planned) is list and len(planned) == 1, 'plan_pairs')
        require(type(planned[0]) is dict and planned[0].get('task') == WORK_TASK
                and planned[0].get('case_id') == 'retry-work' and planned[0].get('arms') == list(ARM_ORDERS[0]),
                'plan_pair', **where)
        pairs = report.get('pairs')
        require(type(pairs) is list and len(pairs) <= 1, 'result_pairs')
        if len(pairs) != 1 or report['status'] != 'completed':
            incomplete.append({'code': 'run_not_completed'})
        integrity = report.get('checks')
        require(type(integrity) is dict, 'integrity_type')
        for key in (*INTEGRITY, 'fixture_unchanged'):
            require(key not in integrity or type(integrity[key]) is bool, 'integrity_field_type')
            if integrity.get(key) is not True:
                incomplete.append({'code': 'integrity_unconfirmed', 'check': key})
        for pair in pairs:
            require(type(pair) is dict and pair.get('task') == WORK_TASK and pair.get('case_id') == 'retry-work',
                    'pair_identity', **where)
            location = {**where, 'phase': 'work'}
            work = pair.get('work')
            check_phase(work, 'work', location, incomplete)
            check_work_oracle(pair.get('work_verification'), location, incomplete, failures, prelude=True)
            check_work_observation(pair.get('work_observation'), work, location, incomplete)
            checkpoint = pair.get('work_checkpoint_sha256')
            require(checkpoint is None or (type(checkpoint) is str and bool(checkpoint)), 'checkpoint_shape', **where)
            if checkpoint is None:
                incomplete.append({'code': 'work_checkpoint_missing', **where})
            arms = pair.get('arms')
            require(type(arms) is list and len(arms) <= 2, 'arms_type', **where)
            if len(arms) != 2:
                incomplete.append({'code': 'arms_missing', **where})
            for j, arm in enumerate(arms):
                arm_name = ARM_ORDERS[0][j]
                location = {**where, 'arm': arm_name}
                require(type(arm) is dict and arm.get('arm') == arm_name, 'arm_identity', **location)
                recorded = arm.get('checkpoint_sha256')
                require(recorded is None or (type(recorded) is str and bool(recorded)), 'checkpoint_shape', **location)
                if recorded is None or recorded != checkpoint:
                    incomplete.append({'code': 'checkpoint_unconfirmed', **location})
                kinds = ('continuation',) if arm_name == 'control' else ('compact', 'continuation')
                phases = arm.get('phases')
                require(type(phases) is list and len(phases) <= len(kinds), 'phases_type', **location)
                if len(phases) != len(kinds):
                    incomplete.append({'code': 'phases_missing', **location})
                for phase, kind in zip(phases, kinds):
                    check_phase(phase, kind, {**location, 'phase': kind}, incomplete)
                observed += check_work_oracle(arm.get('verification'), location, incomplete, failures)
        verdict = 'run_incomplete' if incomplete else 'behavior_failed' if failures else 'accepted'
        return result(verdict, scenario, observed, incomplete + failures)
    except InvalidResult as error:
        return result('invalid_result', scenario, observed, [error.reason])
