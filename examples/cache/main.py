"""Run a small ASGI application that uses Titanspan Cache.
"""  # fmt: skip

import sys

from fastapi.testclient import TestClient

from titanspan.cache import CacheServiceProvider
from titanspan.facades.cache import Cache
from titanspan.foundation import Application


def main() -> None:
    """Run two requests against an application-owned memory cache.
    """  # fmt: skip
    application = Application(
        config={
            "app": {"name": "cache-example"},
            "cache": {
                "default": "memory",
                "stores": {"memory": {"driver": "memory"}},
            },
        },
        service_providers=(CacheServiceProvider(),),
    )

    async def summary() -> dict[str, int]:
        """Count the request and return its cached summary.
        """  # fmt: skip
        views = await Cache.increment_async("page-views")
        greeting = await Cache.remember_async(
            "greeting",
            ttl=60,
            callback=lambda: "Welcome to Titanspan",
        )
        return {"page_views": views, "greeting_length": len(greeting)}

    application.router.get("/summary", summary)

    with TestClient(application.asgi) as client:
        first = client.get("/summary").json()
        second = client.get("/summary").json()

    sys.stdout.write(f"{first}\n{second}\n")


if __name__ == "__main__":
    main()
