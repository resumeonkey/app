import os
from functools import lru_cache

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    path = os.path.join(PROMPTS_DIR, f"{name}.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
