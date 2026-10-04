"""Single-call approval for the exact pending ACR fixture operation."""
import re


def approve_fixture(event, phase, workspace, approved):
    p = event.get('params', {})
    meta, schema = p.get('_meta', {}), p.get('requestedSchema')
    match = re.fullmatch(r'Allow the acr MCP server to run tool "(list_files|read_file|write_file|check)"\?', p.get('message', ''))
    if (phase.kind != 'continuation' or not phase.turn_id or event.get('method') != 'mcpServer/elicitation/request'
            or p.get('threadId') != phase.thread_id or p.get('turnId') != phase.turn_id
            or p.get('serverName') != 'acr' or p.get('mode') != 'form'
            or meta.get('codex_approval_kind') != 'mcp_tool_call' or not match
            or schema != {'type': 'object', 'properties': {}}):
        raise ValueError('out_of_scope_approval')
    tool, args = match.group(1), meta.get('tool_params')
    if type(args) is not dict:
        raise ValueError('invalid_tool_arguments')
    if tool in ('list_files', 'check'):
        valid = args == {}
    else:
        valid = (set(args) == ({'path', 'content'} if tool == 'write_file' else {'path'})
                 and args.get('path') == 'plan.py')
        path = workspace / 'plan.py'
        valid = valid and not path.is_symlink() and path.resolve().parent == workspace.resolve()
        if tool == 'write_file':
            valid = valid and type(args.get('content')) is str and len(args['content'].encode()) <= 100_000
    pending = [item for item in phase.pending_tools.values()
               if item.get('server') == 'acr' and item.get('tool') == tool and item.get('arguments') == args]
    if not valid or len(phase.pending_tools) != 1 or len(pending) != 1 or pending[0]['id'] in approved:
        raise ValueError('approval_pending_call_mismatch')
    approved.add(pending[0]['id'])
    return {'action': 'accept', 'content': {}}
