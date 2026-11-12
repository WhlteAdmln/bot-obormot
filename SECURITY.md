# Security Policy

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Use GitHub's private vulnerability reporting feature if it is enabled for this
repository. Open the repository's Security tab and select "Report a
vulnerability".

If private vulnerability reporting is unavailable, contact the repository
maintainers privately through GitHub. Do not publish vulnerability details
until the maintainers have had an opportunity to investigate.

When reporting a vulnerability, include:

- A description of the affected component and potential impact.
- Steps to reproduce the issue.
- The affected version or commit, if known.
- Any suggested mitigation, if available.

Please do not include real Telegram bot tokens, API keys, passwords, personal
data, or sensitive user uploads in your report.

## Supported Versions

Security fixes are provided for the latest released version. Older releases
are not supported. Please upgrade to the latest release before reporting an
issue, unless the vulnerability itself prevents upgrading.

## Scope and Security Considerations

bot-obormot is a Telegram chatbot that communicates with an LLM server and
uses audiodoc for audio and document processing. Security reports concerning
the following areas are particularly welcome:

- Telegram bot token, LLM credentials, and audiodoc API key handling.
- Telegram access control and unauthorized access to user or chat data.
- Prompt construction, LLM interactions, and unintended exposure of secrets
  or private user content.
- Message and file handling, download validation, and temporary files.
- Path traversal, arbitrary file access, and unsafe subprocess execution.
- Denial of service through malformed or resource-intensive requests.
- Exposure of secrets, user content, or sensitive data in logs and errors.

## Safe Testing

Only test systems and deployments you own or have explicit permission to
assess. Use synthetic or non-sensitive messages and files when testing input
handling. Avoid actions that disrupt service availability, access other
users' data, or modify production files.
