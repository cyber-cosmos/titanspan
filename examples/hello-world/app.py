"""Run a minimal FastAPI application through Titanspan's lifecycle.

The example uses the native ASGI application directly to demonstrate
interoperability with FastAPI.
"""

from fastapi import FastAPI

from titanspan import Application

__all__ = ["app"]

# Keep the native FastAPI object available for routers and server tooling.
app: FastAPI = Application().asgi


@app.get("/")
async def hello_world() -> dict[str, str]:
    """Return a small JSON response from the runnable example.

    Returns:
        The framework name and greeting shown by the Hello World guide.
    """
    return {"framework": "Titanspan", "message": "Hello, world!"}
