# Security Notes

Security-sensitive rules enforced by the current foundation:

- import URLs are validated before use
- onboarding token URLs are redacted in previews and diagnostics
- proxy credentials are kept out of plain-text metadata files
- saved profile passwords are kept out of plain-text metadata files
- diagnostics support bundle export redacts common secret patterns
- secret handling is isolated behind a dedicated store interface

libsecret integration remains an adapter concern and should fail explicitly
rather than silently storing secrets in plain-text files.
