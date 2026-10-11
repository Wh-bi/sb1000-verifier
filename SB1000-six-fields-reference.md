# California SB 1000: the latent-disclosure fields, in practice

**A field-by-field engineering reference for the AI disclosure requirement that now
applies to every covered provider serving California — with no monthly-active-user
threshold.**

**Five fields are required now; a sixth arrives on 1 January 2029. SB 1000 also
replaced the old "AI detection tool" duty with a "disclosure verification tool"
duty — and expressly permits a qualifying third-party tool to satisfy it.**

*Not legal advice. This is a technical field-completeness reference. See the disclaimer at the end.*

---

## Why this document exists

**Where this lives in the code.** The California AI Transparency Act is codified in
the **Business and Professions Code at § 22757.1 and following** — not in the Civil Code.
It was enacted by SB 942 (2024) and amended by AB 853 (2025) and now SB 1000 (2026).

California SB 1000 amends the California AI Transparency Act (SB 942 / AB 853). It was
signed on **30 September 2026 and took effect immediately** — it is not a law with a
future commencement date.

Two changes in it matter to anyone building disclosure tooling:

1. **The 1,000,000-monthly-active-user threshold is gone.** Every developer of a
   generative AI system offered to Californians is now a covered provider. If you assumed
   the Act did not reach you because you are small, that assumption expired on 30 September.
2. **The statutory "free AI detection tool" duty was replaced by a "disclosure
   verification tool" duty**, and the scope now covers content the system **altered**, not
   only content it generated.

Point 2 is the reason this document is worth writing down. "AI detection" — is this image
synthetic? — is a crowded field with well-funded incumbents. "Disclosure verification" —
does this file actually carry the statutory fields? — is nearly empty. They are different
questions, and only the second one is what the Act now asks for.

For **latent** disclosures (the disclosure travels inside the file rather than being
printed on the image), the statute enumerates exactly what the disclosure must contain.
That list is short, specific, and easy to get wrong — not because it is hard to read,
but because "does my file actually carry this?" is a different question from
"did my pipeline set this?"

This document answers the second question for each field, with the on-disk markers that
actually show up in practice.

---

## The statutory fields — five now, six from 1 January 2029

SB 1000 requires the latent disclosure to convey the following. Four were carried over
from the earlier Act; one is new under SB 1000; one begins in 2029. I have kept the
statutory lettering so you can map each row back to the text.

| # | Field | Required | What it means operationally |
|---|---|---|---|
| **A** | Name of the covered provider | now | Identifies **you**, the provider — not the model vendor, not the CDN |
| **B** | Name and version information of the GenAI system | now | Identifies **the system** and **its version** — both parts |
| **C** | Time and date of the content's creation or alteration | now | A timestamp, not a build date |
| **D** | A unique identifier | now | Unique per item of content |
| **E** | Whether the GenAI system created or altered the content | now (**new under SB 1000**) | The **created-vs-altered** distinction, stated |
| **F** | Assistive-technology status | **on and after 1 January 2029** | Not required yet |

Field **E** is new — the earlier Act did not require the disclosure to say which of the
two things happened. Field **F** is the one people miss twice: once by not implementing
it, and once by panicking about it. A file that omits F today is not incomplete today.

Two further requirements now attach to the disclosure itself:

- It must be **permanent, or extraordinarily difficult to remove or tamper with**.
- It must be **compatible with the provider's disclosure verification tool**, and
  **compliant or interoperable with widely recognized industry standards** — which in
  practice means C2PA and the container formats below.

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

## The tool duty — and why third-party verification matters

SB 1000 replaced the earlier Act's "AI detection tool" duty with a **"disclosure
verification tool"** duty. The distinction is the whole point:

- **AI detection** asks: *is this content synthetic?* Crowded field, well-funded
  incumbents, probabilistic answers.
- **Disclosure verification** asks: *does this content carry the provenance data the
  statute requires?* Nearly empty field, deterministic answers, and it is the question
  the Act actually asks.

What the duty requires of a covered provider:

- Make the tool available **at no cost** to users.
- It must let users assess whether image, video, or audio was **created or altered** by
  the provider's system.
- It must **output system provenance data**, accept **content upload or a URL**, and be
  invocable **without visiting the provider's website**.
- **Minor modifications are excluded** from the created/altered assessment — cropping,
  resizing, and color changes do not count as alterations.
- The tool must **not output personal information** detected in the content unless the
  person concerned expressly consents after specified notice.
- Personal information derived from tool users or processed content may not be collected,
  used, retained, sold, or shared beyond what compliance strictly requires.
- Access to the GenAI system or the tool may not be conditioned on providing more
  personal information than compliance strictly requires.
- Providers must **collect user feedback** on the tool's efficacy and act on it.

**And the clause that changes the build-versus-buy calculus:**

> Providers are **expressly allowed to satisfy the disclosure verification tool
> requirement through a qualifying third-party tool.**

Read that alongside the disclosure requirement that latent disclosures be *compatible
with the provider's disclosure verification tool*. The statute is describing a
verification interface, and it permits that interface to be someone else's product.

---

## Link-based disclosures are allowed

The disclosure may be made *"either directly or through a link to a permanent internet
website."* So a latent disclosure may legitimately be a URL rather than the fields inline.

Consequences a verifier has to handle:

- A URL-only payload is **not** automatically incomplete.
- But "permanent" is doing real work in that sentence, and SB 1000 hardened it further
  (permanent or extraordinarily difficult to remove or tamper with). A signed, expiring
  CDN URL is a weak candidate.
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

A field-completeness check answers: **does the disclosure carry the statutory fields?**

It does not answer: **is the disclosure true?**

A file can carry a perfectly complete set of fields naming a provider that did not make
it. Field presence and truthfulness are separate verification problems, and conflating
them is how compliance tooling produces false confidence.

---


---

## How to check a file

The reference implementation behind this document is a single-file, dependency-free
Python script:

```
python sb1000_verify.py yourfile.png
python sb1000_verify.py --json yourfile.mp4
```

It reports, per field: `present` / `missing` / `not_yet_required`, plus a summary
verdict. It reads the file locally and sends nothing anywhere.

Repository: https://github.com/Wh-bi/sb1000-verifier

Hosted API if you would rather not run anything locally:

- `POST https://wanhetools.top/api/v1/verify-sb1000` - file verification
- `POST https://wanhetools.top/api/v1/check` - text compliance check (free, no key)
- `GET  https://wanhetools.top/api/v1/rules` - the full rule set with statutory citations
- `https://wanhetools.top/openapi.json` - machine-readable spec

---

## Summary of the traps

1. **`claim_generator` often names a library, not a provider.** Check the value.
2. **`\b` in a version regex returns truncated matches** (`1.2.3` → `1.2`, `v2.5.0` → `5.0`)
   rather than failing. Use lookarounds, and keep both the two- and three-component forms.
3. **Field E is new under SB 1000** — the created-vs-altered statement was not required before.
4. **Field F is a 2029 requirement.** Do not report it as a current gap.
5. **Minor modifications are excluded** — cropping, resizing, and color changes are not alterations.
6. **The disclosure must be tamper-resistant and tool-compatible**, not merely present.
7. **Link-based disclosure is permitted** — a URL is not automatically non-compliant.
8. **"Technically feasible" is in the statute.** Missing fields are evidence, not verdicts.
9. **Field completeness ≠ truthfulness.** Two different problems.
10. **A qualifying third-party tool can satisfy the tool duty.** You do not have to build it.

---

*This document is a technical reference to a statutory field list. It is not legal advice
and does not create an attorney–client relationship. Section numbering follows California
Business and Professions Code § 22757.1 et seq. as amended by SB 1000. Verify the current statutory text before
relying on it. Not affiliated with or endorsed by the State of California.*
