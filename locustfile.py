from __future__ import annotations

import random
import string

from locust import HttpUser, between, task


def random_alias(prefix: str = "load") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}-{suffix}"


class ShortenerUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def create_short_link(self) -> None:
        alias = random_alias()
        self.client.post(
            "/links/shorten",
            json={
                "original_url": f"https://example.com/load/{alias}",
                "custom_alias": alias,
            },
            name="POST /links/shorten",
        )

    @task(2)
    def search_short_link(self) -> None:
        self.client.get(
            "/links/search",
            params={"original_url": "https://example.com/load/sample"},
            name="GET /links/search",
        )

    @task(1)
    def healthcheck(self) -> None:
        self.client.get("/health", name="GET /health")
