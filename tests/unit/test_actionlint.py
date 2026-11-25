"""Test integrity checks for the pinned GitHub workflow validator.

The tests use in-memory archives so they never download or execute a
third-party binary.
"""

import hashlib
import io
import tarfile

import pytest
from scripts.ci.actionlint import (
    ACTIONLINT_VERSION,
    ActionlintInstallError,
    extract_binary,
    verify_digest,
)

pytestmark = pytest.mark.unit
EXPECTED_DIGEST_ERROR_COUNT = 2


def _archive_with_binary(contents: bytes) -> bytes:
    """Build a deterministic tarball containing one actionlint executable.

    Args:
        contents: Executable bytes stored in the test archive.

    Returns:
        Gzip-compressed archive bytes for extraction tests.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo("actionlint")
        member.size = len(contents)
        archive.addfile(member, io.BytesIO(contents))
    return buffer.getvalue()


def test_actionlint_version_is_pinned() -> None:
    """Use a fixed tool release instead of a moving latest tag.

    The same release is recorded in the checksum-backed installer.
    """
    assert ACTIONLINT_VERSION == "1.7.12"


def test_archive_digest_check_accepts_and_rejects_data() -> None:
    """Accept verified bytes and reject a mismatched release digest.

    Exercise both outcomes using deterministic test bytes.
    """
    archive = b"verified release archive"
    digest = hashlib.sha256(archive).hexdigest()

    assert verify_digest(archive, digest)
    assert not verify_digest(archive, "0" * 64)


def test_extractor_reads_only_the_actionlint_file() -> None:
    """Extract the executable payload without writing archive paths.

    This keeps archive member names away from the filesystem extraction API.
    """
    archive = _archive_with_binary(b"tool payload")

    assert extract_binary(archive) == b"tool payload"


def test_extractor_rejects_an_archive_without_the_executable() -> None:
    """Reject a checksum-valid archive with no expected executable entry.

    Release integrity alone does not replace validating the archive shape.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo("unexpected")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))

    with pytest.raises(ActionlintInstallError, match="one actionlint"):
        extract_binary(buffer.getvalue())


def test_extractor_rejects_invalid_archive_data() -> None:
    """Convert malformed archive bytes into a clear installation error.

    Invalid release data must fail before a workflow checker is executed.
    """
    with pytest.raises(ActionlintInstallError, match="invalid actionlint"):
        extract_binary(b"not a tar archive")
