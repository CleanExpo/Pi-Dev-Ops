#!/usr/bin/env python3
"""Provision the real pinned scanner into an explicit job directory, without sudo.

Release provenance: https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1
Digests are the publisher's release-asset SHA256 values. An unsupported host or
checksum mismatch fails closed; existing journal refusal controls remain unchanged.
"""
import hashlib
import io
import os
import platform
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSION = "8.30.1"
DIGESTS = {
    ("Linux", "x86_64"): ("linux_x64", "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"),
    ("Linux", "aarch64"): ("linux_arm64", "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080"),
    ("Darwin", "arm64"): ("darwin_arm64", "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5"),
    ("Darwin", "x86_64"): ("darwin_x64", "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709"),
}


def main(dest):
    target, expected = DIGESTS[(platform.system(), platform.machine())]
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_{target}.tar.gz"
    with urllib.request.urlopen(url, timeout=60) as response:
        archive = response.read()
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected:
        raise RuntimeError("Gitleaks release checksum mismatch")
    # Extract only the named regular binary; no archive paths or links are followed.
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        member = tar.getmember("gitleaks")
        if not member.isfile():
            raise RuntimeError("Gitleaks archive binary is not a regular file")
        binary = tar.extractfile(member).read()
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    exe = dest / "gitleaks"
    if exe.is_symlink():
        raise RuntimeError("refusing symlink destination")
    exe.write_bytes(binary)
    exe.chmod(0o755)
    found = subprocess.check_output([str(exe), "version"], text=True).strip()
    if found != VERSION:
        raise RuntimeError(f"unexpected scanner version: {found}")
    if os.environ.get("GITHUB_PATH"):
        with open(os.environ["GITHUB_PATH"], "a") as stream:
            stream.write(str(dest) + "\n")
    print(f"Gitleaks {found}; source={url}; archive_sha256={actual}; binary_sha256={hashlib.sha256(binary).hexdigest()}")


if __name__ == "__main__":
    main(sys.argv[1])
