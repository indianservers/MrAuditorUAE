"""Prepare the shared UAE/India fixture with an explicit original-account mapping."""

import asyncio

from generic_candidates_preview import main

if __name__ == "__main__":
    asyncio.run(main(bank_scope=True))
