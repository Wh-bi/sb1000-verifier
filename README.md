# SB 1000 Latent-Disclosure Field Verifier

**An open reference implementation for verifying the six latent-disclosure fields required by California SB 1000.**

California **SB 1000** (Chapter 861, Statutes of 2026) was approved and filed **30 September 2026** and took effect **immediately** as an urgency statute. It amends the California AI Transparency Act (Bus. & Prof. Code §§ 22757.1–22757.5) and adds § 22757.4.1.

Two obligations matter for content pipelines:

| Provision | Obligation |
|---|---|
| **§ 22757.2** | A covered provider **shall make available a disclosure verification tool at no cost**, publicly accessible, accepting uploads or a URL, and **supporting an API** |
| **§ 22757.3** | A covered provider **shall include a latent disclosure** in image / video / audio content created or altered by its GenAI system |

This repository is the **reference implementation of the field check** — it answers one narrow question:

> **Are the six statutory fields actually present in this file?**

It is not a C2PA signature validator, and it is not legal advice.

---

## The six fields (§ 22757.3(a)(1))

| # | Field | Statute |
|---|---|---|
| A | Name of the covered provider | § 22757.3(a)(1)(A) |
| B | Name and version information of the GenAI system | § 22757.3(a)(1)(B) |
| C | Time and date of the content's creation or alteration | § 22757.3(a)(1)(C) |
| D | A unique identifier | § 22757.3(a)(1)(D) |
| E | Whether the GenAI system created or altered the content | § 22757.3(a)(1)(E) |
| F | Whether the system is designed to primarily function as assistive technology — **on and after 1 January 2029** | § 22757.3(a)(1)(F) |

The statute also allows the disclosure to be conveyed **"either directly or through a link to a permanent internet website"** — so a *link-based* disclosure is a lawful implementation, and this verifier checks for it.

Other conditions checked:

* § 22757.3(a)(2) — permanent or extraordinarily difficult to remove or tamper with
* § 22757.3(a)(3) — compatible with the provider's disclosure verification tool
* § 22757.3(a)(4) — compliant or interoperable with widely recognized industry standards

---

## Quick start

```bash
python3 sb1000_verify.py path/to/image.jpg
```

Output (abridged):

```json
{
  "level": "complete",
  "counts": { "required_now": 5, "present": 5, "absent": 0, "future_requirement": 1 },
  "fields": [
    { "key": "provider_name",       "status": "present",
      "evidence": [{ "context": "claim_generator=..." }] },
    { "key": "system_name_version", "status": "present" },
    { "key": "time_date",           "status": "present" },
    { "key": "unique_id",           "status": "present" },
    { "key": "created_or_altered",  "status": "present" },
    { "key": "assistive_tech",      "status": "not_yet_required" }
  ]
}
```

`level` is one of:

* `complete` — every field required as of today is present
* `partial` — some present, some absent
* `none` — no provenance container detected at all

---

## Judgment boundaries (read this before relying on the output)

These are the rules this implementation uses. They are deliberately conservative.

1. **Presence, not truth.** The verifier reports whether a field is *detectable*. It does not check whether the value is accurate.
2. **Container first.** If no provenance container is found (C2PA/JUMBF, XMP, IPTC IIM, EXIF), the result is `none` regardless of any loose keyword matches.
3. **Durability is a heuristic.** § 22757.3(a)(2) requires permanence. We look for hard-binding and manifest signals; absence of those signals is reported as `not_found`, **not** as a violation.
4. **Field F is date-gated.** Before 1 January 2029 its absence is reported as `not_yet_required` and is excluded from the pass/fail count.
5. **Link-based disclosure counts.** A URL that appears alongside provenance metadata is recorded under the link condition.
6. **A missing field is not automatically a violation.** The statute says *"To the extent it is technically feasible."* Report accordingly.

---

## What this does *not* do

* It does **not** validate C2PA signatures or trust chains.
* It does **not** verify that a disclosure is truthful.
* It does **not** provide legal advice. It is a technical field-completeness check.
* It does **not** claim endorsement or certification by the State of California, the Attorney General, or any agency.

---

## Relationship to other tools

Free provenance tools answer *"is there a Content Credentials manifest, and who signed it?"*

This verifier answers a different question: *"are the six statutory fields present?"* — including two that most export pipelines never write, the **unique identifier** (§ 22757.3(a)(1)(D)) and the **created-or-altered flag** (§ 22757.3(a)(1)(E)).

---

## Hosted API

A hosted version is available if you would rather not run this yourself:

```
POST https://wanhetools.top/api/v1/verify-sb1000
Content-Type: application/json

{ "file_base64": "<base64>", "filename": "output.png" }
```

Free tier: 60 requests/minute per IP. The API is stateless — submitted content is checked and not stored.

Full statutory breakdown, FAQ and the hosted verifier:
**https://wanhetools.top/sb1000**

Partnership or licensing enquiries: **https://wanhetools.top/partners** (contact form, no email needed)

---

## Legal

* Statute: [SB 1000, Chapter 861, Statutes of 2026](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB1000)
* This project is an independent implementation. It is not affiliated with, endorsed by, or certified by the State of California.
* **Not legal advice.**

## License

The verifier and this specification are released under the MIT License. See `LICENSE`.

*(The hosted service's rule sets for other jurisdictions are separate and not covered by this repository.)*

## Scope of this licence

This licence covers the reference verifier (`sb1000_verify.py`) and the field
specification in this repository, which implement publicly available statutory
requirements of California SB 1000 (Chapter 861, Statutes of 2026).

It does not cover the hosted service's rule sets for other jurisdictions, which
are separate works and are not distributed here.

This project is an independent implementation. It is not affiliated with,
endorsed by, or certified by the State of California, the California Attorney
General, or any government agency. It does not provide legal advice.
