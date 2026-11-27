---
title: "Document processor"
---

<span id="document-processor"></span>

This example receives a multipart document, validates its category, applies
two ordered transformations, and stores the result under the application root.
It also dispatches an event and logs safe storage metadata.

## Run the application

The application factory uses the current directory as its project root.
Run it from a directory where the process can create `storage/documents`:

```sh
uv run uvicorn --factory examples.document_processor:create_asgi_app --reload
```

Check the health route and submit a local text file:

```sh
curl http://127.0.0.1:8000/health
curl -F category=guides -F document=@README.md \
  http://127.0.0.1:8000/documents
```

The route validates `category` through the application Validation service.
Invalid values receive a safe HTTP 422 response. The request owns the parsed
upload and closes its temporary file after response transmission.

The request-scoped `DocumentProcessor` uses the native Container, Pipeline,
Filesystem, Events, Config, and Logging components. Foundation starts these
services through one application lifecycle and closes them during shutdown.

For another root, call `create_application(Path("/path/to/project"))` and
serve its `.asgi` host with an ASGI server. The application does not change
the process working directory.

The [installed-package runtime check](/titanspan/specifications/foundation/)
runs this workflow against the built wheel. It also runs the installed
controller generator and dispatches the generated action through Routing.
The check also substitutes Storage, Events, Logging, and outgoing HTTP in a
scoped application context. It verifies that fake storage does not write to
the configured local disk and checks a password hash through the application
Hasher.
