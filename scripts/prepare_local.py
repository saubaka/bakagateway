"""Create random secrets without printing them or replacing an existing install."""

import argparse
import os
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--secrets-dir", default=".secrets")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
directory = (root / args.secrets_dir).resolve()
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
directory.chmod(0o700)
for name in ["db_password", "db_admin_password", "app_key"]:
    file = directory / name
    try:
        fd = os.open(file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o400)
    except FileExistsError:
        if file.is_symlink() or len(file.read_text().strip()) < 32:
            raise SystemExit(f"Invalid existing secret: {name}; refusing to replace it")
        continue
    with os.fdopen(fd, "w") as stream:
        stream.write(secrets.token_urlsafe(48) + "\n")
    # Local Compose uses bind-mounted secrets; allow the non-root API user to read
    # the individual file. Host traversal is protected by its 0700 parent directory.
    file.chmod(0o444)
print("Local secrets are ready. No accounts or default passwords were created.")
