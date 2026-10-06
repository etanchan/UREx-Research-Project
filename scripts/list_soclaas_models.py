#!/usr/bin/env python3
"""NUS SoCLaaS Model Discovery & Verification Utility.

Queries the SoCLaaS API `/models` endpoint to list all available open-weight models,
and optionally verifies model responsiveness.

Usage:
    python3 scripts/list_soclaas_models.py
    python3 scripts/list_soclaas_models.py --test-model <model_id>
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

# Ensure urex_benchmark is importable if run directly from repository
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from urex_benchmark.providers.soclaas import _load_env_file


def get_credentials():
    _load_env_file()
    api_key = os.environ.get("SOCLAAS_API_KEY")
    base_url = (os.environ.get("SOCLAAS_BASE_URL") or "https://soclaas-api.comp.nus.edu.sg/v1").rstrip("/")
    return api_key, base_url


def list_models(api_key: str, base_url: str):
    endpoint = f"{base_url}/models"
    req = urllib.request.Request(
        url=endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "UREx-Benchmark/1.0",
        },
        method="GET",
    )

    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
    print(f"Connecting to: {endpoint} ...")
    print(f"Using API Key: {masked_key} (length: {len(api_key)})")

    if not api_key.startswith("clsk_"):
        print(f"WARNING: SoCLaaS API keys typically start with 'clsk_'. Your key starts with '{api_key[:5]}'.")

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"\nError fetching models: HTTP {e.code} - {e.reason}")
        print(f"Server message: {err_body}")
        if "API key authentication failed" in err_body or e.code in (401, 503):
            print("\nTroubleshooting:")
            print("1. In your current terminal session, run: source ~/.zshrc")
            print("2. Check what key is currently loaded: echo $SOCLAAS_API_KEY")
            print("3. Or create a .env file in this directory:")
            print("     echo 'SOCLAAS_API_KEY=clsk_your_actual_key' > .env")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection failed: {e.reason}")
        print("Note: Ensure you are on the NUS VPN if accessing outside campus.")
        sys.exit(1)

    models = data.get("data", [])
    if not models and isinstance(data, list):
        models = data

    print("\n" + "=" * 70)
    print(f"{'MODEL ID':<35} | {'OWNED BY':<15} | {'CREATED'}")
    print("=" * 70)

    for m in models:
        mid = m.get("id", "unknown")
        owner = m.get("owned_by", "-")
        created_ts = m.get("created")
        created_str = "-"
        if created_ts:
            try:
                created_str = datetime.datetime.fromtimestamp(created_ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                pass
        print(f"{mid:<35} | {owner:<15} | {created_str}")

    print("=" * 70)
    print(f"Total available models: {len(models)}")
    print("\nTo run the UREx benchmark with one of these models:")
    print("  python3 -m urex_benchmark.runner --provider soclaas --model-id <MODEL_ID>")
    print("=" * 70 + "\n")


def test_model(api_key: str, base_url: str, model_id: str):
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "Respond with exactly: SoCLaaS connection successful."}
        ],
        "max_tokens": 50,
        "temperature": 0.0,
    }

    req = urllib.request.Request(
        url=endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "UREx-Benchmark/1.0",
        },
        method="POST",
    )

    print(f"Testing model '{model_id}' at {endpoint}...")
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"Reply: {reply.strip()}")
            print("[OK] Model is responsive!")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[FAIL] HTTP {e.code}: {e.reason}\n{err_body}")
    except Exception as e:
        print(f"[FAIL] {e}")


def main():
    parser = argparse.ArgumentParser(description="Discover and test models hosted on NUS SoCLaaS.")
    parser.add_argument("--test-model", type=str, help="Run a quick 1-turn ping test on a model ID.")
    args = parser.parse_args()

    api_key, base_url = get_credentials()
    if not api_key:
        print("ERROR: SOCLAAS_API_KEY is not set.")
        print("Please export SOCLAAS_API_KEY in your shell or set it in a .env file.")
        sys.exit(1)

    if args.test_model:
        test_model(api_key, base_url, args.test_model)
    else:
        list_models(api_key, base_url)


if __name__ == "__main__":
    main()
