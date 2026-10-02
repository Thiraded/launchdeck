"""launchdeck_core.py — pure logic for the launchdeck dashboard.

The code lives in `deck/core/` (map: Docs/architecture.md "Core modules").
This module is the stable facade every frontend, .bat and test imports:
`core.X` reads and `core.X = ...` writes (so `mock.patch.object(core, X)`)
go to the submodule that OWNS X, which is where its callers look it up.

Key concepts
-----------
* A group has no state of its own -- its selection is the logical OR of its
  children: group selected iff any child is selected.
* Running state `[-]` is the work's Job Object when the deck launched it,
  else detected live from the process CommandLine (token = runner basename
  or explicit `match`). It is shown separately from selection.
* registry.json records each launch (root PID + runner) so Stop can find
  the work again.
"""
import json  # noqa: F401  (re-exported for callers/tests: core.os, core.subprocess ...)
import os  # noqa: F401
import subprocess  # noqa: F401
import sys
import threading  # noqa: F401
import time  # noqa: F401
import types
from pathlib import Path  # noqa: F401

from deck.core import (ansi, common, detect, jobs, kill, launch, manifest, model,
                       steps, store, windows)

_MODULES = (common, manifest, store, steps, ansi, detect, kill, windows, model, launch)


def _owned(mod):
    """Top-level names *mod* binds itself (def/class/assignment, not imports)."""
    import ast
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        yield x.id


_OWNER = {}
_PRIOR: dict = {}   # name -> stack of values replaced through the facade
for _m in _MODULES:
    for _n in _owned(_m):
        if _n in _OWNER and _OWNER[_n] is not _m:
            raise ImportError(f"{_n} defined in both {_OWNER[_n].__name__} and {_m.__name__}")
        _OWNER[_n] = _m


class _Facade(types.ModuleType):
    def __getattr__(self, name):  # only called for names not set on the facade
        m = _OWNER.get(name)
        if m is None:
            raise AttributeError(f"module 'launchdeck_core' has no attribute {name!r}")
        return getattr(m, name)

    # mock.patch sees an owned name as "not local" to the facade, so it
    # undoes a patch with delattr instead of setattr(original). Each set
    # pushes the owner's previous value; delete pops it back.
    def __setattr__(self, name, value):
        m = _OWNER.get(name)
        if m is None:
            return super().__setattr__(name, value)
        _PRIOR.setdefault(name, []).append(getattr(m, name))
        setattr(m, name, value)

    def __delattr__(self, name):
        m = _OWNER.get(name)
        if m is None:
            return super().__delattr__(name)
        stack = _PRIOR.get(name)
        if not stack:
            raise AttributeError(f"cannot delete {name!r}: owned by {m.__name__}")
        setattr(m, name, stack.pop())

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(_OWNER))


sys.modules[__name__].__class__ = _Facade
