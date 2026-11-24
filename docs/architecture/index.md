# Architecture

Titanspan is a modular monolith. The framework owns its application APIs,
lifecycle, conventions, and testing helpers while mature libraries own
underlying infrastructure.

The current application foundation uses FastAPI, Dishka, and Pydantic
Settings. Other modules in the architecture are documented boundaries, not
implemented APIs.

Read the complete
[architecture guide](https://github.com/Cyber-Cosmos/titanspan/blob/main/ARCHITECTURE.md)
and the [architecture decision records](./decisions/).
