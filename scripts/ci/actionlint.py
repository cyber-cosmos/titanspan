"""Run a checksum-pinned actionlint binary against repository workflows.

Downloads are cached under the ignored repository cache directory and are
verified against hashes from the upstream release checksum manifest.
"""

from __future__ import annotations

import hashlib
import io
import platform
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ACTIONLINT_VERSION = "1.7.12"
# Archive hashes match the official actionlint release checksum manifest.
ACTIONLINT_DIGESTS = {
    ("Linux", "x86_64"): (
        "linux_amd64",
        "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
    ),
    ("Darwin", "arm64"): (
        "darwin_arm64",
        "aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f",
    ),
    ("Darwin", "x86_64"): (
        "darwin_amd64",
        "5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644",
    ),
}
DOWNLOAD_TIMEOUT_SECONDS = 30
MAXIMUM_ARCHIVE_BYTES = 64 * 1024 * 1024

__all__ = [
    "ACTIONLINT_DIGESTS",
    "ACTIONLINT_VERSION",
    "ActionlintInstallError",
    "extract_binary",
    "main",
    "verify_digest",
]


class ActionlintInstallError(RuntimeError):
    """Describe a failed or unverifiable actionlint installation.

    CI validation must stop rather than continue without workflow syntax
    validation when the pinned tool cannot be installed safely.
    """


def verify_digest(archive: bytes, expected_digest: str) -> bool:
    """Compare an archive's SHA-256 value with its verified release digest.

    Args:
        archive: Downloaded release archive bytes.
        expected_digest: Lowercase SHA-256 digest from the official release.

    Returns:
        Whether the bytes match the pinned digest.
    """
    actual_digest = hashlib.sha256(archive).hexdigest()
    return actual_digest == expected_digest


def extract_binary(archive_bytes: bytes) -> bytes:
    """Read the actionlint executable from a verified tar archive.

    Args:
        archive_bytes: Archive bytes whose digest has already been verified.

    Returns:
        The executable's byte content.

    Raises:
        ActionlintInstallError: If the archive has no unique executable file.
    """
    try:
        with tarfile.open(
            fileobj=io.BytesIO(archive_bytes),
            mode="r:gz",
        ) as tar:
            candidates = [
                member
                for member in tar.getmembers()
                if member.isfile() and Path(member.name).name == "actionlint"
            ]
            if len(candidates) != 1:
                reason = "release archive needs one actionlint executable"
                raise ActionlintInstallError(reason)
            extracted = tar.extractfile(candidates[0])
            if extracted is None:
                reason = "release archive executable cannot be read"
                raise ActionlintInstallError(reason)
            with extracted:
                return extracted.read()
    except tarfile.TarError as exc:
        reason = f"invalid actionlint release archive: {exc}"
        raise ActionlintInstallError(reason) from exc


def _download_archive(asset_name: str) -> bytes:
    """Download the pinned actionlint release over HTTPS.

    Args:
        asset_name: Release asset suffix selected for the current platform.

    Returns:
        Archive bytes from the upstream actionlint release.

    Raises:
        ActionlintInstallError: If the network request fails.
    """
    url = (
        "https://github.com/rhysd/actionlint/releases/download/"
        f"v{ACTIONLINT_VERSION}/actionlint_{ACTIONLINT_VERSION}_"
        f"{asset_name}.tar.gz"
    )
    try:
        # This URL is assembled from a fixed HTTPS origin and pinned release.
        request = Request(url, method="GET")  # noqa: S310
        with urlopen(  # noqa: S310
            request,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            archive = response.read(MAXIMUM_ARCHIVE_BYTES + 1)
    except (OSError, URLError) as exc:
        reason = f"cannot download pinned actionlint from {url}: {exc}"
        raise ActionlintInstallError(reason) from exc

    if len(archive) > MAXIMUM_ARCHIVE_BYTES:
        reason = "actionlint release archive exceeds the size limit"
        raise ActionlintInstallError(reason)
    return archive


def _pinned_binary(root: Path) -> Path:
    """Return a cached binary after checking its pinned release digest.

    Args:
        root: Repository root containing the ignored ``.cache`` directory.

    Returns:
        Path to the executable matching the current platform and version.

    Raises:
        ActionlintInstallError: If the platform is unsupported or install fails.
    """
    key = (platform.system(), platform.machine().lower())
    platform_asset = ACTIONLINT_DIGESTS.get(key)
    if platform_asset is None:
        reason = f"actionlint {ACTIONLINT_VERSION} is not pinned for {key}"
        raise ActionlintInstallError(reason)

    asset_name, expected_digest = platform_asset
    cache_directory = (
        root / ".cache" / "ci-tools" / f"actionlint-{ACTIONLINT_VERSION}"
    )
    archive_path = cache_directory / f"actionlint_{asset_name}.tar.gz"
    binary_path = cache_directory / "actionlint"
    try:
        archive = (
            archive_path.read_bytes()
            if archive_path.is_file()
            else _download_archive(asset_name)
        )
    except OSError as exc:
        reason = f"cannot read cached actionlint archive: {exc}"
        raise ActionlintInstallError(reason) from exc
    if not verify_digest(archive, expected_digest):
        reason = f"actionlint archive failed SHA-256 verification: {asset_name}"
        raise ActionlintInstallError(reason)

    binary = extract_binary(archive)
    try:
        cache_directory.mkdir(parents=True, exist_ok=True)
        temporary_archive = archive_path.with_suffix(".tmp")
        temporary_archive.write_bytes(archive)
        temporary_archive.replace(archive_path)
        temporary_path = binary_path.with_suffix(".tmp")
        temporary_path.write_bytes(binary)
        temporary_path.chmod(0o755)
        temporary_path.replace(binary_path)
    except OSError as exc:
        reason = f"cannot cache actionlint at {binary_path}: {exc}"
        raise ActionlintInstallError(reason) from exc
    return binary_path


def main() -> int:
    """Run actionlint against every workflow in the repository.

    Structural policy checks run separately. This command validates GitHub's
    expression syntax, job references, matrices, and local action metadata.
    """
    root = Path(__file__).resolve().parents[2]
    try:
        executable = _pinned_binary(root)
        # Only the executable extracted from the checksum-verified release
        # archive is run, with fixed arguments and no shell interpolation.
        result = subprocess.run(  # noqa: S603
            [str(executable), "-color"],
            check=False,
            cwd=root,
            timeout=120,
        )
    except (ActionlintInstallError, OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    if result.returncode != 0:
        return result.returncode
    sys.stdout.write(f"actionlint {ACTIONLINT_VERSION} passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
