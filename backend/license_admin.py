from __future__ import annotations

import argparse
import json
import os
import sys

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Admin client for the Kidsnote license server.")
    parser.add_argument("--server-url", default=os.environ.get("KIDSNOTE_LICENSE_SERVER_URL", "http://127.0.0.1:8890"))
    parser.add_argument("--admin-token", default=os.environ.get("KIDSNOTE_LICENSE_ADMIN_TOKEN", "dev-admin-token"))
    sub = parser.add_subparsers(dest="command", required=True)

    issue = sub.add_parser("issue")
    issue.add_argument("--order-id", default="")
    issue.add_argument("--note", default="")

    revoke = sub.add_parser("revoke")
    revoke.add_argument("license_key")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    headers = {"x-admin-token": args.admin_token}
    if args.command == "issue":
        response = requests.post(
            f"{args.server_url.rstrip('/')}/api/v1/admin/licenses/issue",
            json={"order_id": args.order_id, "note": args.note},
            headers=headers,
            timeout=10,
        )
    else:
        response = requests.post(
            f"{args.server_url.rstrip('/')}/api/v1/admin/licenses/revoke",
            json={"license_key": args.license_key},
            headers=headers,
            timeout=10,
        )
    try:
        payload = response.json()
    except Exception:
        payload = {"status_code": response.status_code, "text": response.text}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if response.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
