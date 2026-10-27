"""Explicit-project Compose maintenance and offline, matched-version recovery.

Requires Python 3.9+ and Docker Compose. Never prints credentials or SQL errors.
Backups contain secrets: keep them private, encrypted at rest and off-host.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ("app_key", "db_password", "db_admin_password")
PAYLOADS = {"database.dump", "volumes.tar", *("secrets/" + x for x in SECRETS)}


class OperationError(Exception):
    pass


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_archive(path):
    """No symlinks, devices, traversal or duplicate paths, including in trusted dumps."""
    seen = set()
    with tarfile.open(path) as archive:
        for member in archive:
            p = PurePosixPath(member.name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or not p.parts
                or p.parts[0] not in {"data", "keys"}
                or not (member.isfile() or member.isdir())
                or str(p) in seen
            ):
                raise OperationError("Unsafe volume archive")
            seen.add(str(p))
    if "keys/oidc.json" not in seen:
        raise OperationError("Signing key missing from backup")


def validate_backup(directory):
    manifest_file = directory / "manifest.json"
    if directory.is_symlink() or manifest_file.is_symlink():
        raise OperationError("Backup must use regular files")
    manifest = json.loads(manifest_file.read_text())
    if manifest.get("format") != 1 or set(manifest.get("sha256", {})) != PAYLOADS:
        raise OperationError("Unsupported or incomplete backup")
    for name in PAYLOADS:
        file = directory / name
        if (
            file.is_symlink()
            or file.parent.is_symlink()
            or not file.is_file()
            or checksum(file) != manifest["sha256"][name]
        ):
            raise OperationError("Backup integrity check failed")
    for name in SECRETS:
        if len((directory / "secrets" / name).read_text().strip()) < 32:
            raise OperationError("Invalid backup secret")
    validate_archive(directory / "volumes.tar")
    return manifest


class Compose:
    def __init__(self, args):
        self.project = args.project
        self.docker = shlex.split(args.docker_command)
        self.command = shlex.split(args.compose_command) + [
            "--project-name",
            args.project,
        ]
        if args.env_file:
            self.command += ["--env-file", str(Path(args.env_file).resolve())]
        for profile in args.profile:
            self.command += ["--profile", profile]
        for file in args.file or [str(ROOT / "compose.yaml")]:
            self.command += ["-f", str(Path(file).resolve())]

    def run(self, *args, input_file=None, output_file=None, docker=False):
        command = (self.docker if docker else self.command) + list(args)
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdin=input_file if input_file else subprocess.DEVNULL,
            stdout=output_file if output_file else subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            # Docker/SQL error text can contain supplied values. Do not echo it.
            raise OperationError(
                "Docker operation failed; inspect private operator logs"
            )
        return result.stdout or b""

    def config(self):
        return json.loads(self.run("config", "--format", "json"))

    def running(self):
        return self.run("ps", "--services", "--status", "running").decode().split()


ARCHIVE = """
import sys, tarfile
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as t:
    t.add('/app/data', arcname='data')
    t.add('/app/keys', arcname='keys')
"""
EXTRACT = """
import sys, tarfile, os
from pathlib import Path
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as t:
    for m in t:
        p = Path(m.name)
        if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] not in {'data','keys'} or not (m.isfile() or m.isdir()):
            raise SystemExit('Unsafe archive')
        t.extract(m, path='/app', filter='data')
for folder in ['/app/data', '/app/keys']:
    for current, dirs, files in os.walk(folder):
        os.chown(current, 10001, 10001)
        for name in files:
            os.chown(os.path.join(current, name), 10001, 10001)
"""


def backup(compose, output):
    destination = output.resolve()
    if ROOT in destination.parents:
        raise OperationError("Store backups outside the source workspace")
    if output.exists() or output.is_symlink():
        raise OperationError("Backup destination must not exist")
    config = compose.config()
    active = [name for name in ["web", "api"] if name in compose.running()]
    if "api" not in active or "db" not in compose.running():
        raise OperationError("Backup requires a running API and database")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".backup-", dir=output.parent))
    try:
        (stage / "secrets").mkdir(mode=0o700)
        for name in SECRETS:
            source = Path(config["secrets"][name]["file"])
            if source.is_symlink() or len(source.read_text().strip()) < 32:
                raise OperationError("Invalid source secret")
            shutil.copyfile(source, stage / "secrets" / name)
            (stage / "secrets" / name).chmod(0o600)
        # Operator must suspend external maintenance/CLI writers during this window.
        compose.run("stop", "web", "api")
        with (stage / "database.dump").open("wb") as stream:
            compose.run(
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                "bakagateway",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                output_file=stream,
            )
        with (stage / "volumes.tar").open("wb") as stream:
            compose.run(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--user",
                "root",
                "--entrypoint",
                "python",
                "api",
                "-c",
                ARCHIVE,
                output_file=stream,
            )
        validate_archive(stage / "volumes.tar")
        migration = (
            compose.run(
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "postgres",
                "-d",
                "bakagateway",
                "-Atc",
                "SELECT version_num FROM alembic_version",
            )
            .decode()
            .strip()
        )
        env = config["services"]["api"]["environment"]
        manifest = {
            "format": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - host Python 3.9
            "migration": migration,
            "public_url": env["BG_PUBLIC_URL"],
            "images": {
                name: config["services"][name]["image"] for name in ["api", "web", "db"]
            },
            "sha256": {name: checksum(stage / name) for name in sorted(PAYLOADS)},
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for name in PAYLOADS | {"manifest.json"}:
            (stage / name).chmod(0o600)
        validate_backup(stage)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if active:
            compose.run("start", *reversed(active))


def fresh_target(compose, config):
    for resource in ["ps", "volume ls"]:
        args = shlex.split(resource) + [
            "-q",
            "--filter",
            "label=com.docker.compose.project=" + compose.project,
        ]
        if resource == "ps":
            args.insert(1, "-a")
        if compose.run(*args, docker=True).strip():
            raise OperationError(
                "Restore requires a fresh Compose project with no containers or volumes"
            )
    for name in ["database", "uploads", "signing_keys"]:
        value = config["volumes"][name]
        if value.get("external") or value.get("name") != compose.project + "_" + name:
            raise OperationError("Restore requires private default project volumes")
        if compose.run(
            "volume",
            "ls",
            "-q",
            "--filter",
            "name=^" + re.escape(value["name"]) + "$",
            docker=True,
        ).strip():
            raise OperationError("Target volume already exists")


def restore(compose, directory):
    manifest = validate_backup(directory)
    config = compose.config()
    fresh_target(compose, config)
    env = config["services"]["api"]["environment"]
    if env["BG_PUBLIC_URL"] != manifest["public_url"]:
        raise OperationError("Restore must preserve the original public issuer")
    if any(
        config["services"][n]["image"] != image
        for n, image in manifest["images"].items()
    ):
        raise OperationError(
            "Restore with the backup's matching image names first; upgrade afterwards"
        )
    destinations = {name: Path(config["secrets"][name]["file"]) for name in SECRETS}
    parents = {p.parent for p in destinations.values()}
    if len(parents) != 1:
        raise OperationError("Restore needs one fresh private secrets directory")
    parent = next(iter(parents))
    if parent.exists() or parent.is_symlink():
        raise OperationError("Restore secrets directory must not exist")
    parent.mkdir(parents=True, mode=0o700)
    for name, destination in destinations.items():
        with destination.open("xb") as stream:
            stream.write((directory / "secrets" / name).read_bytes())
        destination.chmod(0o444)
    compose.run("up", "-d", "--wait", "db")
    with (directory / "database.dump").open("rb") as stream:
        compose.run(
            "exec",
            "-T",
            "db",
            "pg_restore",
            "-U",
            "postgres",
            "--role=bakagateway",
            "--no-owner",
            "--no-acl",
            "--single-transaction",
            "--exit-on-error",
            "-d",
            "bakagateway",
            input_file=stream,
        )
    with (directory / "volumes.tar").open("rb") as stream:
        compose.run(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--user",
            "root",
            "--entrypoint",
            "python",
            "api",
            "-c",
            EXTRACT,
            input_file=stream,
        )
    compose.run("up", "-d", "--wait")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project", required=True, help="Explicit Compose project name"
    )
    parser.add_argument(
        "--file", action="append", help="Compose file, repeat for configuration overlays"
    )
    parser.add_argument("--env-file")
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--compose-command", default="docker compose")
    parser.add_argument("--docker-command", default="docker")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("status")
    commands.add_parser("maintenance")
    commands.add_parser("backup").add_argument("--output", required=True, type=Path)
    commands.add_parser("restore").add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", args.project):
        parser.error("Invalid project name")
    # A host-local operator lock; never auto-break a possibly active lock.
    locks = ROOT / ".runtime" / "operations-locks"
    locks.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = locks / (args.project + ".lock")
    try:
        lock.mkdir()
    except FileExistsError:
        raise SystemExit(
            "Another operation holds this project's lock; inspect it before retrying"
        )
    (lock / "owner.json").write_text(
        json.dumps({"pid": os.getpid(), "action": args.action})
    )
    os.umask(0o077)
    try:
        compose = Compose(args)
        if args.action == "status":
            print(
                json.dumps(
                    {"project": args.project, "running_services": compose.running()}
                )
            )
        elif args.action == "maintenance":
            for command in ["oauth-cleanup", "auth-cleanup", "avatar-cleanup"]:
                compose.run(
                    "exec", "-T", "api", "flask", "--app", "app:create_app", command
                )
        elif args.action == "backup":
            backup(compose, args.output.absolute())
        else:
            restore(compose, args.input.absolute())
        print(json.dumps({"action": args.action, "completed": True}))
    except (OperationError, OSError, ValueError, tarfile.TarError, KeyError):
        raise SystemExit(
            "Operation failed safely; check private configuration and documented prerequisites"
        ) from None
    finally:
        shutil.rmtree(lock)


if __name__ == "__main__":
    main()
