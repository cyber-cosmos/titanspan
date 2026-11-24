"""Minimal FastAPI application built on the Titanspan foundation."""

from fastapi import FastAPI

from titanspan import Application

app: FastAPI = Application().asgi


@app.get("/")
async def hello_world() -> dict[str, str]:
    """Return a JSON greeting from the example application."""
    return {"framework": "Titanspan", "message": "Hello, world!"}
