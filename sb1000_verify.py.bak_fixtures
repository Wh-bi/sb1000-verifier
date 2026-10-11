#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sb1000_verify.py — California SB 1000 latent-disclosure field verifier.

Reference implementation. Verifies whether the six latent-disclosure fields
required by Cal. Bus. & Prof. Code section 22757.3(a)(1) are present in an
image / video / audio file.

Statute: SB 1000, Chapter 861, Statutes of 2026 (approved and filed 2026-09-30,
urgency, effective immediately).
Official text: https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB1000

NOT legal advice. This is a technical field-completeness check.
Not affiliated with, endorsed by, or certified by the State of California.

Usage:
    python3 sb1000_verify.py <file> [--json]
    python3 sb1000_verify.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

__version__ = "2.0.0"

ASSISTIVE_TECH_FROM = "2029-01-01"

# ── Section 22757.3(a)(1) — the six statutory fields ────────────────────────
REQUIRED_FIELDS = [
    ("provider_name", "(A) Name of the covered provider"),
    ("system_name_version", "(B) Name and version information of the GenAI system"),
    ("time_date", "(C) Time and date of the content's creation or alteration"),
    ("unique_id", "(D) A unique identifier"),
    ("created_or_altered", "(E) Whether the GenAI system created or altered the content"),
    ("assistive_tech",
     "(F) Assistive-technology status (on and after January 1, 2029)"),
]

PATTERNS = {
    "provider_name": [
        r"c2pa\.claim_generator", r"claim_generator", r"\bsigner\b",
        r"xmp:CreatorTool", r"photoshop:Credit", r"IPTC:Credit",
        r"\bprovider\b", r"\bgenerator\b", r"\bproducer\b",
    ],
    "system_name_version": [
        r"\bsoftwareAgent\b", r"\bSoftware\b", r"\bModel\b", r"\bVersion\b",
        r"xmp:CreatorTool", r"\bgenerator\b.*\d+\.\d+",
        # NOTE: do not use \b around dotted versions — \b does not behave as
        # expected next to '.', which silently drops matches.
        r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])",
        r"(?<![\d.])\d+\.\d+(?![\d.])",
        r"midjourney|dall[\s\-]?e|stable[\s\-]?diffusion|firefly|flux|sora|veo|runway|kling|imagen",
    ],
    "time_date": [
        r"\bdateTime\b", r"\bCreateDate\b", r"\bModifyDate\b", r"\bTimestamp\b",
        r"20\d\d-\d\d-\d\d", r"\d{4}:\d\d:\d\d \d\d:\d\d:\d\d",
    ],
    "unique_id": [
        r"\binstanceID\b", r"\bDocumentID\b", r"\bOriginalDocumentID\b",
        r"\bunique_?id\b", r"\buuid\b", r"urn:uuid:",
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}",
    ],
    "created_or_altered": [
        r"digitalSourceType", r"trainedAlgorithmicMedia",
        r"compositeWithTrainedAlgorithmicMedia", r"algorithmicMedia",
        r"\bcreated\b", r"\baltered\b", r"\bgenerated\b", r"\bsynthetic\b",
        r"c2pa\.actions?", r"createdBy|changedBy",
    ],
    "assistive_tech": [
        r"assistive[\s\-]?tech", r"\baccessibility\b", r"\ba11y\b",
        r"assistiveTechnology", r"screen[\s\-]?reader",
    ],
}

# Section 22757.3(a)(1) — "either directly or through a link to a permanent
# internet website"
LINK_PATTERNS = [
    r"https?://[^\s\"'<>]{8,}", r"c2pa\.soft_binding",
]
# Section 22757.3(a)(4) — compliant or interoperable with widely recognized
# industry standards
STANDARD_PATTERNS = [
    r"\bc2pa\b", r"content[\s\-]?credentials", r"\bIPTC\b",
    r"digitalSourceType", r"\bXMP\b", r"\bISO\s?22144\b",
]
# Section 22757.3(a)(2) — permanent or extraordinarily difficult to remove
DURABILITY_PATTERNS = [
    r"jumbf", r"\bhard[\s\-]?binding\b", r"\bsoft[\s\-]?binding\b",
    r"\bwatermark\b", r"c2pa\.assertions", r"\bmanifest\b",
]

CONTAINERS = {
    "c2pa_jumbf": [b"jumbf", b"c2pa", b"urn:uuid:"],
    "xmp": [b"<x:xmpmeta", b"<rdf:RDF", b"xmlns:x=", b"<xmp:"],
    "iptc_iim": [b"Photoshop 3.0", b"8BIM"],
    "exif": [b"Exif\x00\x00"],
    "png_text": [b"tEXt", b"iTXt", b"zTXt"],
}


def sniff(blob: bytes):
    kind = "unknown"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        kind = "png"
    elif blob[:3] == b"\xff\xd8\xff":
        kind = "jpeg"
    elif blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        kind = "webp"
    elif blob[:6] in (b"GIF87a", b"GIF89a"):
        kind = "gif"
    elif blob[:4] == b"fLaC":
        kind = "flac"
    elif blob[:3] == b"ID3" or blob[:2] in (b"\xff\xfb", b"\xff\xf3"):
        kind = "mp3"
    elif blob[4:8] == b"ftyp":
        kind = "mp4/mov"
    low = blob.lower()
    containers = [n for n, sigs in CONTAINERS.items()
                  if any(s.lower() in low for s in sigs)]
    return kind, containers


def extract_strings(blob: bytes, minlen: int = 4):
    out, cur = [], bytearray()
    for b in blob:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= minlen:
                out.append(cur.decode("ascii", "replace"))
            cur = bytearray()
    if len(cur) >= minlen:
        out.append(cur.decode("ascii", "replace"))
    return out


def _match(hay: str, hay_low: str, patterns, limit: int = 3):
    hits = []
    for rx in patterns:
        try:
            m = re.search(rx, hay_low, flags=re.I)
        except re.error:
            continue
        if m:
            ctx = hay[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            hits.append({"pattern": rx, "context": ctx.strip()[:120]})
        if len(hits) >= limit:
            break
    return hits


def verify(blob: bytes, filename: str = "", today: str | None = None) -> dict:
    if today is None:
        today = time.strftime("%Y-%m-%d")

    kind, containers = sniff(blob)
    strings = extract_strings(blob)
    hay = "\n".join(strings)
    hay_low = hay.lower()
    try:
        hay_low += "\n" + blob.decode("latin-1", "replace").lower()
    except Exception:
        pass

    fields = []
    for key, label in REQUIRED_FIELDS:
        hits = _match(hay, hay_low, PATTERNS.get(key, []))
        if key == "assistive_tech" and today < ASSISTIVE_TECH_FROM and not hits:
            status = "not_yet_required"
        else:
            status = "present" if hits else "absent"
        fields.append({"key": key, "requirement": label, "status": status,
                       "evidence": hits})

    required_now = [f for f in fields if f["status"] != "not_yet_required"]
    present = [f for f in required_now if f["status"] == "present"]
    absent = [f for f in required_now if f["status"] == "absent"]

    conditions = [
        {"key": "link_or_direct",
         "requirement": "s 22757.3(a)(1): either directly or through a link to a "
                        "permanent internet website",
         "status": "present" if _match(hay, hay_low, LINK_PATTERNS, 1)
                   else "not_found",
         "evidence": _match(hay, hay_low, LINK_PATTERNS)},
        {"key": "industry_standards",
         "requirement": "s 22757.3(a)(4)",
         "status": "present" if _match(hay, hay_low, STANDARD_PATTERNS, 1)
                   else "not_found",
         "evidence": _match(hay, hay_low, STANDARD_PATTERNS)},
        {"key": "durability",
         "requirement": "s 22757.3(a)(2)",
         "status": "present" if _match(hay, hay_low, DURABILITY_PATTERNS, 1)
                   else "not_found",
         "evidence": _match(hay, hay_low, DURABILITY_PATTERNS)},
    ]

    if not containers:
        level = "none"
        verdict = ("No provenance container detected (no C2PA/JUMBF, XMP, IPTC or "
                   "EXIF). Not proof of a violation: the statute requires the "
                   "disclosure only to the extent technically feasible, and "
                   "metadata is routinely stripped in transit.")
    elif not absent:
        level = "complete"
        verdict = ("All {} fields required as of {} are present."
                   .format(len(required_now), today))
    else:
        level = "partial"
        verdict = ("Partially complete: {} of {} fields found. Missing: {}"
                   .format(len(present), len(required_now),
                           "; ".join(f["requirement"] for f in absent)))

    return {
        "tool": "sb1000_verify",
        "version": __version__,
        "file": filename or "(unnamed)",
        "bytes": len(blob),
        "file_kind": kind,
        "containers_detected": containers,
        "level": level,
        "verdict": verdict,
        "today": today,
        "fields": fields,
        "conditions": conditions,
        "counts": {
            "required_now": len(required_now),
            "present": len(present),
            "absent": len(absent),
            "future_requirement": len([f for f in fields
                                       if f["status"] == "not_yet_required"]),
        },
        "assistive_tech_required_from": ASSISTIVE_TECH_FROM,
        "legal_reference": ("Cal. Bus. & Prof. Code ss 22757.1-22757.5 and "
                            "22757.4.1 (SB 1000, Chapter 861, Statutes of 2026; "
                            "approved and filed 2026-09-30; urgency statute, "
                            "effective immediately)"),
        "third_party_tool_conditions": [
            "s 22757.2(e)(1) in compliance with this section",
            "s 22757.2(e)(2) compatible with latent disclosures included in "
            "content produced or altered by the covered provider's GenAI system",
            "s 22757.2(e)(3) clearly and conspicuously accessible through the "
            "user interface of the covered provider's GenAI system",
        ],
        "disclaimer": ("Technical verification only, not legal advice. The "
                       "statute requires the disclosure only to the extent it is "
                       "technically feasible; a missing field is not by itself a "
                       "violation. This tool reports whether a disclosure covers "
                       "the statutory fields; it does not verify that the "
                       "disclosure is truthful. Not affiliated with or endorsed "
                       "by the State of California."),
    }


# ── Self-test ──────────────────────────────────────────────────────────────
_OLD, _FUT = "2026-10-09", "2029-06-01"
_FULL = (b"\xff\xd8\xff\xe1" + b"jumbf c2pa urn:uuid:1" +
         b"claim_generator=Adobe Firefly 3.2.1" +
         b"digitalSourceType=trainedAlgorithmicMedia" +
         b"instanceID=xmp.iid:12345678-1234-1234-1234-123456789abc" +
         b"CreateDate=2026:10:09 08:00:00" + b"\x00" * 8 + b"\xff\xd9")

SELFTEST = [
    ("all five fields (2026 view)", _FULL, _OLD, "complete"),
    ("same file, 2029 view (field F missing)", _FULL, _FUT, "partial"),
    ("link-based disclosure", b"\xff\xd8\xff\xe1jumbf c2pa "
     b"https://example.com/provenance/abc claim_generator=Acme 1.0.0 "
     b"digitalSourceType=trainedAlgorithmicMedia "
     b"instanceID=xmp.iid:abcdef01-2345-6789-abcd-ef0123456789 "
     b"CreateDate=2026:10:09 08:00:00" + b"\x00" * 8 + b"\xff\xd9",
     _OLD, "complete"),
    ("clean file", b"\x89PNG\r\n\x1a\n" + b"\x00" * 60, _OLD, "none"),
]


def _selftest() -> int:
    ok = fail = 0
    for name, blob, day, expect in SELFTEST:
        r = verify(blob, "sample", today=day)
        if r["level"] == expect:
            ok += 1
            print("  ok   {:<42} level={}".format(name, r["level"]))
        else:
            fail += 1
            print("  FAIL {:<42} level={} (expected {})"
                  .format(name, r["level"], expect))
    print("\n  {}/{} passed".format(ok, ok + fail))
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="California SB 1000 latent-disclosure field verifier")
    ap.add_argument("file", nargs="?", help="image / video / audio file")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if not a.file or not os.path.isfile(a.file):
        ap.error("give a file path, or use --selftest")

    with open(a.file, "rb") as f:
        blob = f.read()
    r = verify(blob, os.path.basename(a.file))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("file      : {}".format(r["file"]))
        print("level     : {}".format(r["level"]))
        print("verdict   : {}".format(r["verdict"]))
        print()
        for f_ in r["fields"]:
            ev = ("  e.g. " + f_["evidence"][0]["context"][:60]) if f_["evidence"] else ""
            print("  {:<22} {}{}".format(f_["key"], f_["status"], ev))
        print()
        for c in r["conditions"]:
            print("  {:<22} {}".format(c["key"], c["status"]))
        print("\n" + r["disclaimer"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
