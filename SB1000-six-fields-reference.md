# California SB 1000: the six latent-disclosure fields, in practice

**A field-by-field engineering reference for the AI transparency disclosure requirement
that took effect on 1 October 2026.**

*Not legal advice. This is a technical field-completeness reference. See the disclaimer at the end.*

---

## Why this document exists

California SB 1000 (the California AI Transparency Act) added Section 22757.3 to the
Civil Code. Covered providers of generative AI systems must make an AI disclosure
available to a person who views or receives content the system generated or altered.

For **latent** disclosures (the disclosure travels inside the file, rather than being
printed on the image), the statute enumerates exactly what the disclosure must contain.
That list is short, specific, and easy to get wrong — not because it is hard to read,
but because "does my file actually carry this?" is a different question from
"did my pipeline set this?"

This document answers the second question for each field, with the on-disk markers that
actually show up in practice.

**Status:** SB 1000 took effect 1 October 2026. If you ship generated or altered media to
California users, this applies to you now.

---

## The six fields — Section 22757.3(a)(1)

The statute requires the disclosure to include all of the following. I have kept the
statutory lettering so you can map each row back to the text.

| # | Field | What it means operationally |
|---|---|---|
| **A** | Name of the covered provider | Identifies **you**, the provider — not the model vendor, not the CDN |
| **B** | Name and version information of the GenAI system | Identifies **the system** and **its version** — both parts |
| **C** | Time and date of the content's creation or alteration | A timestamp, not a build date |
| **D** | A unique identifier | Unique per item of content |
| **E** | Whether the GenAI system created or altered the content | The **created-vs-altered** distinction, stated |
| **F** | Assistive-technology status | **On and after 1 January 2029** — not required yet |

Field **F** is the one people miss twice: once by not implementing it, and once by
panicking about it. It is a *future* requirement. A file that omits F today is not
incomplete today.

---

## Where each field actually lives on disk

These are the markers a verifier can look for. They come from the container formats that
generated media already uses — C2PA/JUMBF, XMP, and IPTC.

### A. Provider name

```
c2pa.claim_generator          claim_generator          signer
xmp:CreatorTool               photoshop:Credit         IPTC:Credit
provider  generator  producer
```

The trap: `claim_generator` is frequently set to a **library** name
(`c2pa-python 0.5.0`, `c2pa-rs`) rather than the provider. That satisfies a naive string
check and fails the statute. Check what the value *is*, not that the key exists.

### B. System name and version

```
softwareAgent   Software   Model   Version
xmp:CreatorTool   generator + a version number
semantic model names: midjourney dall-e stable-diffusion firefly flux sora veo runway kling imagen
```

**A regex trap that produces wrong answers, not errors.** The obvious pattern for a
version number is:

```python
r"\b\d+\.\d+\b"        # looks reasonable — behaves badly
```

It does not fail loudly. It matches, and returns the **wrong substring**. Measured
behaviour:

| input | match returned |
|---|---|
| `1.2.3` | `1.2` ← truncated |
| `v2.5.0` | `5.0` ← truncated and offset |
| `10.20.30` | `10.20` ← truncated |
| `1.2` | `1.2` ← correct |

The cause is that `\b` is positional with respect to the dot: it fires before the leading
digit but also fires *between* a digit and a following `.`, so the match terminates one
component early — and if the string starts with a letter (`v2.5.0`), the leading boundary
shifts the whole match right.

The consequence for a verifier is subtle and worse than a crash: `2.5.0` gets recorded as
`5.0`. Your check reports a version, so it looks like it worked.

**Use explicit lookarounds, and use both widths.**

```python
r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])"   # 1.2.3
r"(?<![\d.])\d+\.\d+(?![\d.])"        # 1.2
```

Two notes from measuring this:

- The two-component pattern alone will **not** match `1.2.3` — the trailing
  `(?![\d.])` correctly refuses to stop mid-version. Keep the three-component pattern
  alongside it, or you will drop every three-part version.
- Ordering matters if you return only the first match: put the three-component pattern
  first.

### C. Time and date

```
dateTime   CreateDate   ModifyDate   Timestamp
2026-10-01           2026:10:01 12:00:00
```

Use the creation/alteration time. A container-level `ModifyDate` written by your build
step is not the content's creation date.

### D. Unique identifier

```
instanceID   DocumentID   OriginalDocumentID   unique_id   uuid   urn:uuid:
8-4-4-4-12 hex UUID shape
```

`DocumentID` and `OriginalDocumentID` are *not* interchangeable: re-saving an asset often
preserves `OriginalDocumentID` while generating a new `DocumentID`. Either can serve as
the unique identifier, but know which one you are relying on.

### E. Created or altered

```
digitalSourceType
  trainedAlgorithmicMedia
  compositeWithTrainedAlgorithmicMedia
  algorithmicMedia
created  altered  generated  synthetic
c2pa.actions   createdBy  changedBy
```

This is the field with the most semantic content and the least tooling. `digitalSourceType`
is the cleanest signal when present. When it is absent, you are left inferring from
prose — which is exactly the case where a disclosure says something but does not say
**which** of the two things happened.

### F. Assistive-technology status — required on and after 1 January 2029

```
assistive-tech   assistiveTechnology   accessibility   a11y   screen-reader
```

Implement it early if you can; do not report a file as non-compliant today for lacking it.

---

## Link-based disclosures are allowed

Section 22757.3(a)(1) permits the disclosure to be made *"either directly or through a
link to a permanent internet website."* So a latent disclosure may legitimately be a URL
rather than the fields inline.

Consequences a verifier has to handle:

- A URL-only payload is **not** automatically incomplete.
- But "permanent" is doing real work in that sentence. A signed, expiring CDN URL is a
  weak candidate for *permanent*.
- If you verify by following the link, you are now making a network request per asset.
  Decide deliberately whether your verifier does that.

---

## "Technically feasible" is part of the requirement

The statute requires the latent disclosure only **to the extent technically feasible**.
A missing field is therefore not, by itself, a violation — it may be evidence toward one.

That distinction changes what a verifier should output. Reporting "FAIL" is wrong.
The honest output is: *which statutory fields are covered, which are not, and which are
not yet required.*

---

## Fields vs. truth

A field-completeness check answers: **does the disclosure cover the statutory fields?**

It does not answer: **is the disclosure true?**

A file can carry a perfectly complete set of six fields naming a provider that did not
make it. Field presence and truthfulness are separate verification problems, and
conflating them is how compliance tooling produces false confidence.

---

## How to check a file

The reference implementation behind this document is a single-file, dependency-free
Python script:

```
python sb1000_verify.py yourfile.png
python sb1000_verify.py --json yourfile.mp4
```

It reports, per field: `present` / `missing` / `not_yet_required`, plus a summary verdict.
It reads the file locally and sends nothing anywhere.

Repository: https://github.com/Wh-bi/sb1000-verifier

There is also a hosted API if you would rather not run anything locally:

- `POST https://wanhetools.top/api/v1/verify-sb1000` — file verification
- `POST https://wanhetools.top/api/v1/check` — text compliance check (free, no key)
- `GET  https://wanhetools.top/api/v1/rules` — the full rule set with statutory citations
- `https://wanhetools.top/openapi.json` — machine-readable spec

---

## Summary of the traps

1. **`claim_generator` often names a library, not a provider.** Check the value.
2. **`\b` next to `.` breaks version matching.** Use explicit lookarounds.
3. **Field F is a 2029 requirement.** Do not report it as a current gap.
4. **Link-based disclosure is permitted** — a URL is not automatically non-compliant.
5. **"Technically feasible" is in the statute.** Missing fields are evidence, not verdicts.
6. **Field completeness ≠ truthfulness.** Two different problems.

---

*This document is a technical reference to a statutory field list. It is not legal advice
and does not create an attorney–client relationship. Section numbering follows California
Civil Code § 22757.3 as added by SB 1000. Verify the current statutory text before relying
on it. Not affiliated with or endorsed by the State of California.*
