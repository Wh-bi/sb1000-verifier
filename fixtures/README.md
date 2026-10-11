# SB 1000 verifier — test fixtures

**These are structurally faithful fixtures, not cryptographically signed C2PA files.**
Real C2PA signing requires a certificate and the official `c2pa` library; this tool is
dependency-free by design, so it cannot produce signed assets. These fixtures exercise
the verifier's field detection and its behaviour on malformed input.

| file | what it exercises | expected level (2026 view) |
|---|---|---|
| `01-complete.jpg` | All five fields present (provider, system+version, timestamp, unique id, created-or-altered) | `complete` (ok) |
| `02-missing-version.jpg` | Provider and timestamp present, but the system version is absent | `partial` (ok) |
| `03-missing-provider.jpg` | No provider name — only a generic generator string | `partial` (ok) |
| `04-missing-time.jpg` | No creation/alteration timestamp | `partial` (ok) |
| `05-link-based.jpg` | Disclosure is a permanent URL instead of inline fields (permitted by the statute) | `complete` (ok) |
| `06-no-provenance.png` | PNG with no provenance container at all | `none` (ok) |
| `07-truncated.jpg` | JPEG header only — tests the verifier against a malformed/truncated file (must not crash) | `none` (ok) |
