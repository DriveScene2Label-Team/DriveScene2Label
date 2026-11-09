"""Create an invited Cognito team account without sending email or logging passwords."""
import argparse
import os
from pathlib import Path
import re
import secrets
import string

from environment import Environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("--credentials-file", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,60}", args.username):
        raise ValueError("Username must contain 3..60 letters, numbers, dots, dashes or underscores.")
    repository = Path(__file__).resolve().parents[2]
    destination = args.credentials_file.resolve()
    if destination.is_relative_to(repository):
        raise ValueError("Save credentials outside the repository; never commit passwords.")
    environment = Environment()
    pool = environment.foundation["TeamUsers"]
    # Exclusive creation protects any previously delivered account credential.
    handle = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    password = "Aa1!" + "".join(secrets.choice(string.ascii_letters + string.digits + "!@#%_-+") for _ in range(24))
    client = environment.clients["cognito-idp"]
    try:
        client.admin_create_user(UserPoolId=pool, Username=args.username, TemporaryPassword=password, MessageAction="SUPPRESS")
        client.admin_add_user_to_group(UserPoolId=pool, Username=args.username, GroupName="team")
        state, _ = environment.read_control("state")
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            handle = None
            output.write("DriveScene2Label team login\n\nURL: " + state.get("public_url", "See AWS environment status") +
                         "\nUsername: " + args.username + "\nTemporary password: " + password +
                         "\n\nChoose a new password on first login. This temporary password expires in 7 days.\n" +
                         "This is an application account, not an AWS console account. Do not commit or share this file.\n")
        print("Account created. Temporary credential saved locally; first login requires a new password.")
    finally:
        if handle is not None:
            os.close(handle)
            destination.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
