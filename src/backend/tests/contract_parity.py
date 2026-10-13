# mypy: ignore-errors
"""Semantic drift between the hand-written contract and the runtime (drf-spectacular) schema.

Per operation it compares response codes, non-path parameters, request-body presence and the
resolved shape (property names, kinds, enums, nullability, required) of every request/response
body. ``$ref``/``allOf``/nullable ``oneOf`` are resolved, so schema NAMES do not matter.
"""

from __future__ import annotations

from typing import Any

import yaml

METHODS = ("get", "post", "put", "patch", "delete")


def load(p: Any) -> Any:
    with open(p, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def ref(doc, r):
    node = doc
    for part in r.lstrip("#/").split("/"):
        node = node[part]
    return node


def shape(doc, s, depth=0, seen=()):
    if s is None:
        return None
    if "$ref" in s:
        if s["$ref"] in seen:
            return {"recursive": s["$ref"].split("/")[-1]}
        return shape(doc, ref(doc, s["$ref"]), depth, seen + (s["$ref"],))
    if depth > 6:
        return {"deep": True}
    s = dict(s)
    if "oneOf" in s:
        parts = [
            p
            for p in s["oneOf"]
            if not (isinstance(p, dict) and p.get("$ref", "").endswith("NullEnum"))
        ]
        nullable = len(parts) != len(s["oneOf"]) or s.get("nullable", False)
        if len(parts) == 1:
            p = shape(doc, parts[0], depth, seen)
            return {**p, "nullable": nullable or p.get("nullable", False)} if p else p
    if "allOf" in s:
        merged = {"type": "object", "properties": {}, "required": []}
        nullable = s.get("nullable", False)
        for part in s["allOf"]:
            p = shape(doc, part, depth, seen)
            if p is None:
                continue
            if p.get("kind") == "object":
                merged["properties"].update(p["props"])
                merged["required"] += p["required"]
            else:
                return {**p, "nullable": nullable or p.get("nullable", False)}
        for k, v in s.get("properties", {}).items():
            merged["properties"][k] = shape(doc, v, depth + 1, seen)
        merged["required"] += s.get("required", [])
        return {
            "kind": "object",
            "props": merged["properties"],
            "required": sorted(set(merged["required"])),
            "nullable": nullable,
        }
    t = s.get("type")
    out = {"nullable": bool(s.get("nullable", False))}
    if "enum" in s:
        vals = [v for v in s["enum"] if v is not None]
        out["enum"] = sorted(map(str, vals))
        if None in s["enum"]:
            out["nullable"] = True
    if t == "object" or "properties" in s:
        out["kind"] = "object"
        out["props"] = {
            k: shape(doc, v, depth + 1, seen) for k, v in s.get("properties", {}).items()
        }
        out["required"] = sorted(s.get("required", []))
        ap = s.get("additionalProperties")
        if ap not in (None, False):
            out["additional"] = True
    elif t == "array":
        out["kind"] = "array"
        out["items"] = shape(doc, s.get("items"), depth + 1, seen)
    else:
        out["kind"] = t or "any"
        if s.get("format") in ("date-time", "uri", "uuid"):
            out["format"] = s["format"]
    return out


def params(doc, path_item, op):
    res = {}
    for p in path_item.get("parameters", []) + op.get("parameters", []):
        if "$ref" in p:
            p = ref(doc, p["$ref"])
        res[(p["in"], p["name"])] = bool(p.get("required", False))
    # ignore path params presence differences handled separately
    return res


def body_schema(doc, content):
    if content and "$ref" in content:
        content = ref(doc, content["$ref"]).get("content")
    if not content:
        return None
    c = content.get("application/json") or next(iter(content.values()), None)
    return shape(doc, c.get("schema")) if c else None


def ops(doc):
    out = {}
    for path, item in doc["paths"].items():
        for m in METHODS:
            if m in item:
                out[(m, path)] = (item, item[m])
    return out


def diff_shape(a, b, where, out):
    if a == b:
        return
    if a is None or b is None or a.get("kind") != b.get("kind"):
        out.append((where, "kind", (a or {}).get("kind"), (b or {}).get("kind")))
        return
    if a.get("nullable") != b.get("nullable"):
        out.append((where, "nullable", a.get("nullable"), b.get("nullable")))
    if a.get("enum") != b.get("enum") and (a.get("enum") or b.get("enum")):
        out.append((where, "enum", a.get("enum"), b.get("enum")))
    if a.get("kind") == "object":
        ka, kb = set(a["props"]), set(b["props"])
        if ka != kb:
            out.append((where, "props", sorted(ka - kb), sorted(kb - ka)))
        if a["required"] != b["required"]:
            out.append(
                (
                    where,
                    "required",
                    sorted(set(a["required"]) - set(b["required"])),
                    sorted(set(b["required"]) - set(a["required"])),
                )
            )
        for k in ka & kb:
            diff_shape(a["props"][k], b["props"][k], where + "." + k, out)
    elif a.get("kind") == "array":
        diff_shape(a["items"], b["items"], where + "[]", out)


M03 = (
    "/api/queues/",
    "/api/leases/",
    "/api/frames/",
    "/api/issues/",
    "/api/escalations/",
    "/api/decision-cases/",
    "/api/rework/",
    "/api/effort-events/",
    "/api/review-policy/",
    "/api/runs/{id}/",
    "/api/runs/{id}/ranking/",
)


def in_scope(key, scope):
    if scope == "all":
        return True
    return key[1] in M03 or any(key[1].startswith(p) for p in M03[:8])


def compare(docs_path, runtime_path, scope="m03"):
    d, r = load(docs_path), load(runtime_path)
    od, orr = ops(d), ops(r)
    od = {k: v for k, v in od.items() if in_scope(k, scope)}
    orr = {k: v for k, v in orr.items() if in_scope(k, scope)}
    res = {
        "onlyDocs": sorted(set(od) - set(orr)),
        "onlyRuntime": sorted(set(orr) - set(od)),
        "opId": [],
        "codes": [],
        "params": [],
        "body": [],
        "shapes": [],
    }
    for key in sorted(set(od) & set(orr)):
        (di, dop), (ri, rop) = od[key], orr[key]
        if dop.get("operationId") != rop.get("operationId"):
            res["opId"].append((key, dop.get("operationId"), rop.get("operationId")))
        cd, cr = set(dop["responses"]), set(rop["responses"])
        if cd != cr:
            res["codes"].append(
                (key, "docs-only", sorted(cd - cr), "runtime-only", sorted(cr - cd))
            )
        pd, pr = params(d, di, dop), params(r, ri, rop)
        pd_np = {k: v for k, v in pd.items() if k[0] != "path"}
        pr_np = {k: v for k, v in pr.items() if k[0] != "path"}
        # cursor/query/header differences
        if pd_np != pr_np:
            res["params"].append(
                (
                    key,
                    "docs-only",
                    sorted(set(pd_np) - set(pr_np)),
                    "runtime-only",
                    sorted(set(pr_np) - set(pd_np)),
                    "required-diff",
                    sorted(k for k in set(pd_np) & set(pr_np) if pd_np[k] != pr_np[k]),
                )
            )
        bd, br = dop.get("requestBody"), rop.get("requestBody")
        if bool(bd) != bool(br):
            res["body"].append((key, "presence", bool(bd), bool(br)))
        out = []
        if bd and br:
            diff_shape(
                body_schema(d, bd.get("content")), body_schema(r, br.get("content")), "request", out
            )
        for code in sorted(cd & cr):
            rd, rr = dop["responses"][code], rop["responses"][code]
            if "$ref" in rd:
                rd = ref(d, rd["$ref"])
            if "$ref" in rr:
                rr = ref(r, rr["$ref"])
            diff_shape(
                body_schema(d, rd.get("content")),
                body_schema(r, rr.get("content")),
                f"resp{code}",
                out,
            )
        for o in out:
            res["shapes"].append((key,) + o)
    return res
