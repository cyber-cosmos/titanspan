# Hello World

Run the included FastAPI application from the repository root:

```sh
uv sync --locked
uv run uvicorn --app-dir examples/hello-world app:app --reload
```

Visit <http://127.0.0.1:8000/>. The endpoint returns a JSON greeting.

The example uses native FastAPI routing. Titanspan currently supplies the
application lifecycle and Dishka container integration; a fluent routing API
is planned.
