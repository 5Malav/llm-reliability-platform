"""
Smoke test: verify both API keys are valid, funded, and reachable.
Makes one tiny call to each provider and prints the response.
"""

import os
from dotenv import load_dotenv

# Load keys from .env into the environment
load_dotenv()

def test_anthropic():
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY from env automatically

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",   # Haiku = cheapest, per our cost policy
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with exactly: Anthropic OK"}],
    )
    print("✅ Anthropic:", response.content[0].text.strip())


def test_openai():
    from openai import OpenAI

    client = OpenAI()  # reads OPENAI_API_KEY from env automatically

    response = client.chat.completions.create(
        model="gpt-4o-mini",   # cheapest OpenAI chat model
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with exactly: OpenAI OK"}],
    )
    print("✅ OpenAI:", response.choices[0].message.content.strip())


if __name__ == "__main__":
    print("Running smoke test...\n")

    try:
        test_anthropic()
    except Exception as e:
        print("❌ Anthropic FAILED:", e)

    try:
        test_openai()
    except Exception as e:
        print("❌ OpenAI FAILED:", e)

    print("\nDone.")