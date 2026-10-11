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

# ── Which patterns actually prove "version information"? ───────────────────
#  ★ 2026-10-11 加：夹具生成器发现一个假阳 ——
#    `claim_generator=AdobeFirefly`（无版本号）被判为 system_name_version 齐全，
#    因为模式表里的**模型名**模式（firefly）命中了。
#    ⇒ 但「能识别出模型名」不等于"披露含名称 + 版本信息"（法条要两者）。
#  ⇒ 把「能证明版本」的模式单列出来：只有命中它们才算 present；
#    仅命中模型名 ⇒ weak（有证据但不满足）。
VERSION_STRONG = [
    r"\bVersion\b", r"\bsoftwareAgent\b", r"\bSoftware\b", r"\bModel\b",
    r"\bgenerator\b.*\d+\.\d+",
    r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])",
    r"(?<![\d.])\d+\.\d+(?![\d.])",
    r"xmp:CreatorTool",
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
        elif key == "system_name_version" and hits:
            # ★ 只有命中「能证明版本」的模式才算 present；
            #   仅命中纯模型名（如 Firefly）⇒ weak（有证据但不满足"名称+版本"）
            strong = _match(hay, hay_low, VERSION_STRONG)
            status = "present" if strong else "weak"
        else:
            status = "present" if hits else "absent"
        fields.append({"key": key, "requirement": label, "status": status,
                       "evidence": hits})

    required_now = [f for f in fields if f["status"] != "not_yet_required"]
    present = [f for f in required_now if f["status"] == "present"]
    absent = [f for f in required_now if f["status"] == "absent"]
    weak = [f for f in required_now if f["status"] == "weak"]
    # ★ weak 也算"未满足"（否则 complete 判定会把纯模型名当齐全）——
    #   把它并入 absent 的计数，但保留在 fields 里以便输出区分。
    absent = absent + weak

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


# ── Test fixtures (structurally faithful, NOT cryptographically signed) ─────
#  ★ 借鉴 c2pa-scanner 的 `make-testimage` 思路，但明确边界：
#    真 C2PA 签名需要证书 + 官方 c2pa 库（与本工具「零依赖」冲突）
#    ⇒ 这里生成的是**结构夹具**：真实容器头尾 + 在正确嵌入点写入字段。
#    ⇒ 它们能测工具行为，**不能**用于证明"签名有效性"。

FIXTURE_SPECS = [
    # (文件名, 说明, 期望 level（2026 视角）, blob 生成函数键)
    ("01-complete.jpg", "All five fields present (provider, system+version, "
     "timestamp, unique id, created-or-altered)", "complete"),
    ("02-missing-version.jpg", "Provider and timestamp present, but the system "
     "version is absent", "partial"),
    ("03-missing-provider.jpg", "No provider name — only a generic generator "
     "string", "partial"),
    ("04-missing-time.jpg", "No creation/alteration timestamp", "partial"),
    ("05-link-based.jpg", "Disclosure is a permanent URL instead of inline "
     "fields (permitted by the statute)", "complete"),
    ("06-no-provenance.png", "PNG with no provenance container at all", "none"),
    ("07-truncated.jpg", "JPEG header only — tests the verifier against a "
     "malformed/truncated file (must not crash)", "none"),
]


def _jpeg(payload: bytes) -> bytes:
    """Minimal but structurally valid JPEG: SOI + APP11 (JUMBF-ish) + EOI."""
    import struct
    seg = b"JP" + struct.pack(">H", len(payload) + 2) + payload
    return b"\xff\xd8" + b"\xff\xeb" + seg + b"\x00" * 16 + b"\xff\xd9"


def _png() -> bytes:
    """Minimal PNG signature + IHDR-ish bytes, no provenance."""
    import struct
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">I", 13) + struct.pack(">II", 1, 1) + \
        b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00"
    return sig + struct.pack(">I", 13) + ihdr


def build_fixture(idx: int) -> bytes:
    """按编号构造夹具（与 FIXTURE_SPECS 顺序一致）"""
    base = (b"jumbf c2pa urn:uuid:8f14e45f-ceea-467a-9c1c-1a2b3c4d5e6f "
            b"claim_generator=Adobe Firefly 3.2.1 ")
    stamp = b"CreateDate=2026:10:09 08:00:00 "
    uid = b"instanceID=xmp.iid:12345678-1234-1234-1234-123456789abc "
    dst = b"digitalSourceType=trainedAlgorithmicMedia "
    if idx == 0:      # complete
        return _jpeg(base + dst + uid + stamp + b"\x00" * 8)
    if idx == 1:      # missing version (claim_generator without a version)
        return _jpeg(b"jumbf c2pa urn:uuid:8f14e45f-ceea-467a-9c1c-1a2b3c4d5e6f "
                     b"claim_generator=AdobeFirefly " + dst + uid + stamp + b"\x00" * 8)
    if idx == 2:      # missing provider (no claim_generator/CreatorTool at all)
        return _jpeg(b"jumbf c2pa urn:uuid:8f14e45f-ceea-467a-9c1c-1a2b3c4d5e6f "
                     b"softwareAgent=some-model-v2 " + dst + uid + stamp + b"\x00" * 8)
    if idx == 3:      # missing time
        return _jpeg(base + dst + uid + b"\x00" * 8)
    if idx == 4:      # link-based
        return _jpeg(b"jumbf c2pa https://example.com/provenance/abc123 "
                     b"claim_generator=Acme Studio 1.0.0 " + dst + uid + stamp + b"\x00" * 8)
    if idx == 5:      # no provenance
        return _png()
    return b"\xff\xd8\xff\xeb"      # truncated JPEG (header only)


def make_fixtures(outdir: str) -> int:
    os.makedirs(outdir, exist_ok=True)
    lines = ["# SB 1000 verifier — test fixtures", "",
             "**These are structurally faithful fixtures, not cryptographically "
             "signed C2PA files.**",
             "Real C2PA signing requires a certificate and the official `c2pa` "
             "library; this tool is",
             "dependency-free by design, so it cannot produce signed assets. "
             "These fixtures exercise",
             "the verifier's field detection and its behaviour on malformed input.",
             "",
             "| file | what it exercises | expected level (2026 view) |",
             "|---|---|---|"]
    for i, (name, desc, expect) in enumerate(FIXTURE_SPECS):
        blob = build_fixture(i)
        with open(os.path.join(outdir, name), "wb") as f:
            f.write(blob)
        r = verify(blob, name)
        mark = "ok" if r["level"] == expect else "MISMATCH"
        lines.append("| `{}` | {} | `{}` ({}) |".format(name, desc, expect, mark))
        print("  {:<6} {:<24} level={:<9} (expected {})".format(
            mark, name, r["level"], expect))
    with open(os.path.join(outdir, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n  wrote {} fixtures + README.md to {}".format(
        len(FIXTURE_SPECS), outdir))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="California SB 1000 latent-disclosure field verifier")
    ap.add_argument("file", nargs="?", help="image / video / audio file")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--make-fixtures", metavar="DIR", nargs="?",
                    const="fixtures",
                    help="write structurally-faithful test fixtures (NOT signed C2PA files)")
    a = ap.parse_args()

    if a.make_fixtures:
        return make_fixtures(a.make_fixtures)
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
