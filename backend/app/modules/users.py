"""Module 5 — User Simulator.

Maintains a pool of "returning" users (stable user_id + country/device/browser)
and mints fresh "new" users on demand. The returning/new mix is what makes
frequency-cap and user-targeting validation meaningful.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.util import new_id


@dataclass
class SimUser:
    user_id: str
    country: str
    device: str
    browser: str
    returning: bool = False


class UserPool:
    def __init__(self, countries: List[str], devices: List[str], browsers: List[str],
                 pool_size: int = 200, returning_ratio: float = 0.6,
                 rng: Optional[random.Random] = None) -> None:
        self.countries = countries or ["IN", "US", "UK", "CA"]
        self.devices = devices or ["ctv", "mobile", "desktop", "tablet"]
        self.browsers = browsers or ["chrome", "firefox", "safari", "edge"]
        self.returning_ratio = returning_ratio
        self.rng = rng or random.Random()
        self._returning: List[SimUser] = [self._mint(returning=True) for _ in range(max(pool_size, 1))]

    def _mint(self, returning: bool) -> SimUser:
        return SimUser(
            user_id=new_id("user-"),
            country=self.rng.choice(self.countries),
            device=self.rng.choice(self.devices),
            browser=self.rng.choice(self.browsers),
            returning=returning,
        )

    def pick(self) -> SimUser:
        """Return a returning user with probability `returning_ratio`, else a new one."""
        if self._returning and self.rng.random() < self.returning_ratio:
            return self.rng.choice(self._returning)
        return self._mint(returning=False)

    def fixed_user(self, country: str, device: str, browser: str = "chrome") -> SimUser:
        """A single deterministic user (used by the frequency-cap scenario)."""
        return SimUser(new_id("user-"), country, device, browser, returning=True)
