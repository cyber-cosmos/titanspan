---
title: "Architecture"
---

<span id="architecture"></span>

Titanspan is a modular monolith. The framework owns its application APIs,
lifecycle, conventions, and testing helpers while mature libraries own
underlying infrastructure.

The current application foundation uses FastAPI, Dishka, and Pydantic
Settings. Native configuration, logging, HTTP, and Routing use the same
application service registry. Collections provides eager and lazy APIs for
ordinary Python iterables. Other modules remain documented boundaries unless
marked otherwise in the repository's root-level `ARCHITECTURE.md` file.

Read the complete
[architecture guide](https://github.com/titanspan/titanspan/blob/main/ARCHITECTURE.md)
and the [architecture decision records](/titanspan/architecture/decisions/).
