"""Bind observer ABI to the selected release's exact decoder, without server side effects."""
import ast
import math
import struct


def load_decoder(package):
    path=package/'web_hmi/server.py'
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    # Schema4's decoder calls the pure replay helper. Extract both functions
    # without importing the server or starting any service. Old releases have
    # only the original decoder and remain supported.
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and
           n.name in ('decode_nis_replay','decode_observer_trace_hex')]
    assert any(n.name=='decode_observer_trace_hex' for n in nodes)
    scope={'math':math,'struct':struct}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return scope['decode_observer_trace_hex']
