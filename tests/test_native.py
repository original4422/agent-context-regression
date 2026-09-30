from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from context_regression.cli import main
from context_regression.native import Phase, TOKEN_KEYS, check_fork, isolated_config, native_plan
from context_regression.native_client import AppServer


def event(method, **params):
    return {"method": method, "params": {"threadId": "thread", **params}}


def started(turn="new"):
    return event("turn/started", turn={"id": turn, "status": "inProgress"})


def done(turn="new", status="completed"):
    return event("turn/completed", turn={"id": turn, "status": status})


def compact(turn="new", item="compact"):
    return event("item/completed", turnId=turn, item={"id": item, "type": "contextCompaction"})


def usage(value):
    return event("thread/tokenUsage/updated", turnId="new", tokenUsage={"last": {k: value for k in TOKEN_KEYS}, "total": {k: value for k in TOKEN_KEYS}})


class NativeProtocolTests(unittest.TestCase):
    def phase(self, events, kind="compact"):
        p = Phase(kind, "thread", 1, 0, "seed")
        for seq, e in enumerate(events, 1):
            p.consume(e, seq)
        return p

    def test_plan_is_offline_and_keeps_bounded_opposite_order(self):
        out = io.StringIO()
        with patch('subprocess.Popen', side_effect=AssertionError('model started')), redirect_stdout(out):
            main(['native-plan', '--model', 'test-model'])
        plan = json.loads(out.getvalue())
        self.assertEqual((plan['seeds'], plan['compactions'], plan['continuations']), (2, 2, 4))
        self.assertEqual(plan['model_phase_timeout_budget_seconds'], 1020)
        self.assertEqual(plan['pairs'][0]['arms'], plan['pairs'][1]['arms'][::-1])
        self.assertEqual(plan['pairs'][0]['request_sha256'], plan['pairs'][1]['request_sha256'])
        self.assertNotEqual(plan['pairs'][0]['seed_sha256'], plan['pairs'][1]['seed_sha256'])
        for pair in plan['pairs']:
            self.assertNotIn('Checkpoint probe', pair['seed_text'])
            self.assertIn('Do not call tools or modify files yet', pair['seed_text'])

    def test_ack_legacy_and_unmatched_events_are_not_completion(self):
        cases = [[{"id": 1, "result": {}}],
                 [{"id": 1, "result": {}}, event("thread/compacted", turnId="new")],
                 [{"id": 1, "result": {}}, started(), compact("other"), done()],
                 [{"id": 1, "result": {}}, started(), compact(), done("other")],
                 [{"id": 1, "result": {}}, started(), {**compact(), "params": {**compact()['params'], "threadId": "foreign"}}, done()]]
        for events in cases:
            with self.subTest(events=events):
                self.assertFalse(self.phase(events).completed)

    def test_complete_item_and_terminal_with_ack_in_any_order(self):
        for events in ([started(), compact(), compact(), done(), {"id": 1, "result": {}}],
                       [{"id": 1, "result": {}}, started(), done(), compact()]):
            p = self.phase(events)
            self.assertTrue(p.completed)
            self.assertEqual(len(p.compactions), 1)

    def test_failed_compaction_and_rpc_error(self):
        self.assertEqual(self.phase([started(), compact(), done(status='failed')]).failure, 'turn_failed')
        self.assertEqual(self.phase([{"id": 1, "error": {"code": -1}}]).failure, 'rpc_error')

    def test_old_sequence_and_reused_turn_cannot_satisfy_boundary(self):
        p = Phase('compact', 'thread', 1, 5, 'seed')
        for i, e in enumerate([started(), compact(), done(), {"id": 1, "result": {}}], 1):
            p.consume(e, i)
        self.assertFalse(p.completed)
        p.consume(started('seed'), 6)
        self.assertEqual(p.failure, 'turn_boundary_mismatch')

    def test_automatic_compaction_contaminates_seed_or_continuation(self):
        for kind in ('seed', 'continuation'):
            for e in (compact(), event('thread/compacted', turnId='new')):
                self.assertEqual(self.phase([started(), e], kind).failure, 'comparison_contaminated')

    def test_tool_budget_counts_unique_started_items(self):
        calls = [event('item/started', turnId='new', item={'type':'mcpToolCall', 'id':str(i)}) for i in range(17)]
        self.assertIsNone(self.phase([started(), *calls[:16], *calls[:16]], 'continuation').failure)
        self.assertEqual(self.phase([started(), *calls], 'continuation').failure, 'tool_budget')
        self.assertEqual(self.phase([started(), calls[0]], 'seed').failure, 'tool_budget')

    def test_usage_missing_duplicate_and_regression_never_become_totals(self):
        cases = [([], 'missing'), ([usage(10), usage(10)], 'contract_unverified'),
                 ([usage(10), usage(2), usage(12)], 'counter_regression')]
        broken = usage(10)
        broken['params']['tokenUsage']['total'].pop('inputTokens')
        cases.append(([broken, usage(12)], 'missing_fields'))
        null = usage(10)
        null['params']['tokenUsage']['total']['inputTokens'] = None
        cases.append(([null, usage(12)], 'missing_fields'))
        for events, reason in cases:
            with self.subTest(reason=reason):
                p = self.phase([started(), *events])
                self.assertEqual(p.report()['usage_issue'], reason)
                self.assertIsNone(p.report()['usage'])
                self.assertIsNone(p.report()['arm_total'])
                self.assertEqual(len(p.usage_events), len(events))

    def test_fork_preserves_completed_content_and_source(self):
        seed = {'id':'seed-thread', 'turns':[{'id':'seed', 'status':'completed', 'items':[{'id':'i1', 'type':'userMessage', 'content':[{'type':'text', 'text':'policy A', 'text_elements':[]}]}]}]}
        fork = deepcopy(seed)
        fork.update(id='fork-thread', forkedFromId='seed-thread')
        fork['turns'][0]['id'] = 'generated'
        fork['turns'][0]['items'][0]['id'] = 'generated-item'
        check_fork(seed, fork, 'seed')
        for mutate in (lambda f: f.update(forkedFromId='other'),
                       lambda f: f['turns'][0].update(status='inProgress'),
                       lambda f: f['turns'][0]['items'][0]['content'][0].update(text='policy B'),
                       lambda f: f['turns'][0]['items'].append({'type':'contextCompaction','id':'c'})):
            changed = deepcopy(fork)
            mutate(changed)
            with self.assertRaises(ValueError):
                check_fork(seed, changed, 'seed')

    def test_config_constructs_process_and_thread_overrides_without_mutation(self):
        inherited = {'mcp_servers': {'unrelated': {}, 'computer-use': {}, 'acr': {}}, 'plugins': {'p@market': {}}}
        saved = deepcopy(inherited)
        config, args = isolated_config(inherited, ['/python', '/bridge'], 'model', 'low')
        self.assertEqual(inherited, saved)
        for feature in ('apps', 'plugins', 'hooks', 'shell_tool', 'multi_agent'):
            self.assertFalse(config['features.' + feature])
        self.assertFalse(config['mcp_servers.unrelated.enabled'])
        self.assertTrue(config['mcp_servers.acr.enabled'])
        self.assertEqual(config['sandbox_mode'], 'read-only')
        self.assertEqual(config['approval_policy'], 'on-request')
        self.assertEqual(config['approvals_reviewer'], 'user')
        self.assertNotIn('mcp_servers.acr.default_tools_approval_mode', config)
        default, default_args = isolated_config({}, ['/python', '/bridge'], None, 'low')
        self.assertNotIn('model', default)
        self.assertNotIn('model=null', default_args)
        self.assertIn('mcp_servers.computer-use.enabled=false', args)
        self.assertIn('plugins.p@market.enabled=false', args)
        self.assertNotIn('--ignore-user-config', args)
        self.assertNotIn('mcpServerStatus/list', ' '.join(args))


PEER = '''
import json, sys, time
mode = sys.argv[1]
def send(e):
 data=json.dumps(e)
 if mode=='split':
  sys.stdout.write(data[:10]);sys.stdout.flush();time.sleep(.01);data=data[10:]
 print(data, flush=True)
def notify(method, **params):
 send({'method':method, 'params':{'threadId':'thread', **params}})
if mode=='stale':
 notify('turn/started', turn={'id':'old','status':'inProgress'})
 notify('item/completed', turnId='old', item={'id':'old-c','type':'contextCompaction'})
 notify('turn/completed', turn={'id':'old','status':'completed'})
for line in sys.stdin:
 q=json.loads(line)
 if q['method']=='turn/interrupt':
  if mode != 'no-terminal':
   notify('turn/completed', turn={'id':'new','status':'interrupted'})
  continue
 if mode=='eof':
  break
 if mode=='partial-eof':
  print('{',end='',flush=True);break
 if mode=='unexpected':
  send({'id':500, 'method':'mcpServer/elicitation/request','params':{}})
  continue
 if mode in ('no-turn', 'stale'):
  send({'id':q['id'], 'result':{}})
  continue
 if mode=='late':
  time.sleep(.12)
 send({'id':q['id'], 'result':{'turn':{'id':'new'}} if q['method']=='turn/start' else {}})
 notify('turn/started', turn={'id':'new','status':'inProgress'})
 if mode in ('success', 'split'):
  notify('item/completed', turnId='new', item={'id':'c','type':'contextCompaction'})
  notify('turn/completed', turn={'id':'new','status':'completed'})
'''


class NativeClientTests(unittest.TestCase):
    def run_peer(self, mode, kind='compact', cancel=None, timeout=.15, grace=.2):
        with tempfile.TemporaryDirectory() as root:
            trace = []
            host = AppServer([sys.executable, '-u', '-c', PEER, mode], root, trace)
            try:
                result = host.phase(kind, 'thread', {'threadId':'thread'}, timeout, cancel=cancel, grace=grace)
                if result['status'] != 'completed':
                    self.assertIsNotNone(host.process.poll())
                    with self.assertRaisesRegex(RuntimeError, 'client_stopped'):
                        host.phase(kind, 'thread', {'threadId':'thread'}, 1)
                return result, trace
            finally:
                host.close()

    def test_prequeued_old_completion_cannot_join_new_ack(self):
        with tempfile.TemporaryDirectory() as root:
            host = AppServer([sys.executable, '-u', '-c', PEER, 'stale'], root, [])
            try:
                deadline = time.monotonic() + 2
                self.assertTrue(host.selector.select(2))
                # Bytes are readable but have not been consumed by the client.
                self.assertEqual(host.sequence, 0)
                result = host.phase('compact', 'thread', {'threadId':'thread'}, .1, grace=.1)
                self.assertEqual(result['start_sequence'], 3)
                self.assertEqual(result['status'], 'phase_timeout')
                self.assertEqual(result['compaction_item_ids'], [])
                self.assertIsNone(result['turn_id'])
            finally:
                host.close()

    def test_cancel_before_dispatch_closes_without_new_request(self):
        with tempfile.TemporaryDirectory() as root:
            trace, flag = [], threading.Event()
            host = AppServer([sys.executable, '-u', '-c', PEER, 'success'], root, trace)
            flag.set()
            with self.assertRaisesRegex(RuntimeError, 'client_stopped'):
                host.phase('compact', 'thread', {'threadId':'thread'}, 1, cancel=flag)
            self.assertEqual(trace, [])
            self.assertIsNotNone(host.process.poll())

    def test_split_lines_and_eof(self):
        self.assertEqual(self.run_peer('split', timeout=2)[0]['status'], 'completed')
        self.assertEqual(self.run_peer('eof')[0]['status'], 'app_server_closed')
        self.assertEqual(self.run_peer('partial-eof')[0]['status'], 'incomplete_event_at_eof')

    def test_readable_flood_cannot_extend_absolute_deadline(self):
        with tempfile.TemporaryDirectory() as root:
            peer = "import sys\nwhile True: print('{\"method\":\"noise\",\"params\":{}}', flush=True)"
            host = AppServer([sys.executable, '-u', '-c', peer], root, [])
            try:
                self.assertTrue(host.selector.select(2))
                began = time.monotonic()
                result = host.phase('compact', 'thread', {'threadId':'thread'}, .05, grace=.05)
                self.assertEqual(result['status'], 'phase_timeout')
                self.assertLess(time.monotonic() - began, 1)
            finally:
                host.close()

    def test_scripted_success(self):
        self.assertEqual(self.run_peer('success')[0]['status'], 'completed')

    def test_ack_without_turn_times_out_and_closes(self):
        result, _ = self.run_peer('no-turn')
        self.assertEqual(result['status'], 'phase_timeout')
        self.assertEqual(result['cancellation'], 'cancellation_unconfirmed')

    def test_timeout_interrupt_requires_matching_terminal(self):
        self.assertEqual(self.run_peer('active')[0]['cancellation'], 'terminal_confirmed')
        self.assertEqual(self.run_peer('no-terminal')[0]['cancellation'], 'cancellation_unconfirmed')

    def test_cancel_during_start_response_interrupts_late_turn(self):
        with tempfile.TemporaryDirectory() as root:
            flag, trace = threading.Event(), []
            host = AppServer([sys.executable, '-u', '-c', PEER, 'late'], root, trace)
            original = host.send
            def send(method, params):
                result = original(method, params)
                if method == 'turn/start':
                    flag.set()
                return result
            host.send = send
            try:
                result = host.phase('continuation', 'thread', {'threadId':'thread'}, 1, cancel=flag, grace=1)
                self.assertEqual(result['status'], 'cancelled')
                self.assertEqual(result['cancellation'], 'terminal_confirmed')
                self.assertTrue(any(e['message'].get('method') == 'turn/interrupt' for e in trace))
            finally:
                host.close()

    def test_unexpected_approval_stops_without_accepting(self):
        result, _ = self.run_peer('unexpected')
        self.assertEqual(result['status'], 'unexpected_server_request')
        self.assertEqual(result['cancellation'], 'cancellation_unconfirmed')
