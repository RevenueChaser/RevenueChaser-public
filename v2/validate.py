"""The subset of JSON Schema the v2 board schemas use, as a function: ``errors(value, schema) -> list[str]``.

The repository carries no ``jsonschema`` dependency and the v2 contract needs only a handful of keywords, so the
checker is here rather than in requirements: a dependency added for a CI check is a dependency the door and the
Android build inherit. Supported: ``type`` (object, array, string, integer, number, boolean, null, or a list of
them), ``const``, ``enum``, ``required``, ``properties``, ``additionalProperties`` (``false`` only), ``items``,
``minItems``. Anything else in a schema is refused loudly by ``errors`` rather than ignored, so a schema cannot
quietly stop checking.
"""
from __future__ import annotations

_KEYWORDS = {"$schema", "$id", "title", "description", "type", "const", "enum", "required",
             "properties", "additionalProperties", "items", "minItems"}

_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
          "boolean": bool, "null": type(None)}


class SchemaError(ValueError):
    """A schema this checker cannot read — never a problem with the value."""


def errors(value, schema: dict, path: str = "$") -> list[str]:
    """Every way ``value`` breaks ``schema``, as readable lines; an empty list means it validates."""
    unknown = sorted(set(schema) - _KEYWORDS)
    if unknown:
        raise SchemaError(f"{path}: schema keyword(s) this checker does not implement: {', '.join(unknown)}")
    out: list[str] = []
    if "type" in schema:
        out += _type_errors(value, schema["type"], path)
        if out:
            return out               # a wrong type makes every other check noise
    if "const" in schema and value != schema["const"]:
        out.append(f"{path}: {value!r} is not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} is not one of {schema['enum']!r}")
    if isinstance(value, dict):
        out += _object_errors(value, schema, path)
    if isinstance(value, list):
        out += _array_errors(value, schema, path)
    return out


def _type_errors(value, want, path: str) -> list[str]:
    names = [want] if isinstance(want, str) else list(want)
    for name in names:
        if name not in _TYPES:
            raise SchemaError(f"{path}: unknown type {name!r}")
        # ``True`` is an ``int`` in Python and a boolean in JSON; keep the two apart.
        if isinstance(value, bool) != (name == "boolean"):
            continue
        if isinstance(value, _TYPES[name]):
            return []
    return [f"{path}: {type(value).__name__} is not {'/'.join(names)}"]


def _object_errors(value: dict, schema: dict, path: str) -> list[str]:
    out = []
    props = schema.get("properties") or {}
    for key in schema.get("required") or []:
        if key not in value:
            out.append(f"{path}: required key {key!r} is missing")
    if schema.get("additionalProperties") is False:
        for key in sorted(set(value) - set(props)):
            out.append(f"{path}: key {key!r} is not in the schema")
    for key, sub in props.items():
        if key in value:
            out += errors(value[key], sub, f"{path}.{key}")
    return out


def _array_errors(value: list, schema: dict, path: str) -> list[str]:
    out = []
    if "minItems" in schema and len(value) < schema["minItems"]:
        out.append(f"{path}: {len(value)} item(s), fewer than {schema['minItems']}")
    if "items" in schema:
        for i, item in enumerate(value):
            out += errors(item, schema["items"], f"{path}[{i}]")
    return out
