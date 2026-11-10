"""Generic, type-hint driven (de)serialization of simulation state.

All simulation state is made of dataclasses whose fields are primitives, lists,
dicts with string keys, tuples, Optionals and nested dataclasses. Objects refer
to each other by id, so the state tree has no cycles and can be written to JSON
without any per-class code. Fields marked ``transient`` (caches, loaded data)
are skipped and rebuilt after loading.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
import types
import typing
from dataclasses import field
from typing import Any, Union

_HINTS: dict[type, dict[str, Any]] = {}


def transient(default=None, default_factory=None):
    """Declare a dataclass field that is not saved."""
    md = {"transient": True}
    if default_factory is not None:
        return field(default_factory=default_factory, metadata=md, repr=False, compare=False)
    return field(default=default, metadata=md, repr=False, compare=False)


def _hints(cls: type) -> dict[str, Any]:
    h = _HINTS.get(cls)
    if h is None:
        mod = sys.modules.get(cls.__module__)
        h = typing.get_type_hints(cls, globalns=vars(mod) if mod else None)
        _HINTS[cls] = h
    return h


def to_data(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {}
        for f in dataclasses.fields(obj):
            if f.metadata.get("transient"):
                continue
            out[f.name] = to_data(getattr(obj, f.name))
        return out
    if isinstance(obj, (list, tuple)):
        return [to_data(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): to_data(v) for k, v in obj.items()}
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            raise ValueError("non-finite float in simulation state")
        return obj
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    raise TypeError(f"cannot serialize {type(obj).__name__}")


def from_data(tp: Any, data: Any) -> Any:
    origin = typing.get_origin(tp)
    if tp is Any:
        return data
    if origin in (Union, types.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if data is None:
            return None
        if len(args) == 1:
            return from_data(args[0], data)
        for a in args:  # first primitive match
            if isinstance(a, type) and isinstance(data, a):
                return data
        return from_data(args[0], data)
    if origin in (list,):
        (et,) = typing.get_args(tp) or (Any,)
        return [from_data(et, v) for v in data]
    if origin in (tuple,):
        args = typing.get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(from_data(args[0], v) for v in data)
        return tuple(from_data(a, v) for a, v in zip(args, data))
    if origin in (dict,):
        kt, vt = typing.get_args(tp) or (str, Any)
        conv = int if kt is int else str
        return {conv(k): from_data(vt, v) for k, v in data.items()}
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        hints = _hints(tp)
        kwargs = {}
        for f in dataclasses.fields(tp):
            if f.metadata.get("transient") or f.name not in data:
                continue
            kwargs[f.name] = from_data(hints[f.name], data[f.name])
        return tp(**kwargs)
    if tp is float and isinstance(data, int):
        return float(data)
    return data


def dumps(obj: Any) -> str:
    return json.dumps(to_data(obj), separators=(",", ":"), sort_keys=False)


def state_hash(obj: Any) -> str:
    """Stable digest of serialized state (used by determinism tests)."""
    return hashlib.sha256(json.dumps(to_data(obj), sort_keys=True).encode()).hexdigest()[:16]
