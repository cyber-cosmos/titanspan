# Configuration security

Treat all configuration as potentially sensitive. Do not put live secrets in
defaults, examples, committed `.env` files, exception messages, or logs.

`Repository.redacted()` and its representation mask common key patterns such
as passwords, secrets, tokens, API keys, authorization values, cookies,
private keys, and credentials. CLI inspection uses the redacted snapshot.
This is a diagnostic heuristic; it cannot identify every secret or remove
credentials embedded in arbitrary text. Do not log full configuration
mappings.

The configuration cache is plain JSON and can contain secrets. Its default
file permissions are owner-only where supported. Keep its directory private
and out of source control and build artifacts. Use `config:clear` when
removing the generated snapshot.

Python config files execute code with the application's permissions. They
are trusted application code, not a sandbox. The loader restricts discovery
to the configured application root and rejects escaping paths and symlinks,
but it does not make an untrusted Python file safe to execute. Never load
user-uploaded config files.

Dotenv values are parsed without mutating `os.environ`. Process environment
values retain precedence. Settings validation and load errors omit rejected
values and parser details to reduce accidental secret disclosure.
