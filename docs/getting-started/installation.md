# Installation

Titanspan requires Python 3.12 or later and is currently installed from a
source checkout. No PyPI release has been published.

Install [uv](https://docs.astral.sh/uv/), then clone and synchronize the
project:

```sh
git clone https://github.com/Cyber-Cosmos/titanspan.git
cd titanspan
uv sync --locked
uv run titanspan --help
```

The dependency lockfile is committed. Use `uv sync --locked` for reproducible
development and `make help` to discover local tasks.
