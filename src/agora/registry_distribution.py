import base64
import binascii
import hashlib
import io
import re
import stat
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from agora.filesystem import assert_slug
from agora.markdown import parse_markdown, string_attribute
from agora.model import RegistryIndexRecord, RegistryReleaseRecord, RegistryTrustKeyRecord
from agora.trust import decode_trusted_public_key

INDEX_SCHEMA = "agora/registry-index/v1"
SIGNATURE_SCHEMA = "agora/registry-release/v1"
VERSION_PATTERN = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MAX_INDEX_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 2000
MAX_ARCHIVE_PATH = 240
DOWNLOAD_TIMEOUT = 30


@contextmanager
def download_registry_release(
    source: str,
    *,
    version: str | None,
    public_key: str | None,
    require_signature: bool,
    allow_insecure_http: bool,
    trusted_keys: list[RegistryTrustKeyRecord] | None = None,
) -> Iterator[tuple[Path, RegistryIndexRecord, RegistryReleaseRecord, bool, str]]:
    index, release, signature_verified = inspect_registry_release(
        source,
        version=version,
        public_key=public_key,
        require_signature=require_signature,
        allow_insecure_http=allow_insecure_http,
        trusted_keys=trusted_keys,
    )
    archive_source = _resolve_archive_source(index.source, release.archive)
    archive_bytes, resolved_archive = _read_source(
        archive_source,
        maximum=MAX_ARCHIVE_BYTES,
        allow_insecure_http=allow_insecure_http,
        label="registry archive",
    )
    actual_checksum = hashlib.sha256(archive_bytes).hexdigest()
    if actual_checksum != release.sha256:
        raise ValueError(
            f"Registry archive checksum mismatch: expected {release.sha256}, got {actual_checksum}"
        )
    with tempfile.TemporaryDirectory(prefix="agora-registry-download-") as temporary:
        extraction_root = Path(temporary) / "snapshot"
        extraction_root.mkdir()
        _extract_archive(archive_bytes, resolved_archive, extraction_root)
        registry_root = _find_registry_root(extraction_root)
        yield registry_root, index, release, signature_verified, resolved_archive


def inspect_registry_release(
    source: str,
    *,
    version: str | None,
    public_key: str | None,
    require_signature: bool,
    allow_insecure_http: bool,
    trusted_keys: list[RegistryTrustKeyRecord] | None = None,
) -> tuple[RegistryIndexRecord, RegistryReleaseRecord, bool]:
    index_bytes, resolved_index = _read_source(
        source,
        maximum=MAX_INDEX_BYTES,
        allow_insecure_http=allow_insecure_http,
        label="registry index",
    )
    index = load_registry_index(index_bytes, resolved_index)
    release = select_registry_release(index, version)
    signature_verified = verify_release_signature(
        release,
        public_key=public_key,
        require_signature=require_signature,
        trusted_keys=trusted_keys or [],
    )
    return index, release, signature_verified


def load_registry_index(contents: bytes, source: str) -> RegistryIndexRecord:
    try:
        document = parse_markdown(contents.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("Registry index must be UTF-8 Markdown") from error
    attributes = document.attributes
    if string_attribute(attributes, "schema") != INDEX_SCHEMA:
        raise ValueError(f"Registry index schema must be {INDEX_SCHEMA}: {source}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Registry index id")
    name = string_attribute(attributes, "name")
    raw_releases = attributes.get("releases")
    if not isinstance(raw_releases, list) or not raw_releases:
        raise ValueError("Registry index releases must be a non-empty array")
    releases: list[RegistryReleaseRecord] = []
    versions: set[str] = set()
    for raw in raw_releases:
        if not isinstance(raw, dict):
            raise ValueError("Registry index releases must contain objects")
        version = _required_release_string(raw, "version")
        validate_registry_version(version)
        if version in versions:
            raise ValueError(f"Duplicate registry release version: {version}")
        versions.add(version)
        archive = _required_release_string(raw, "archive")
        sha256 = _required_release_string(raw, "sha256")
        if not SHA256_PATTERN.fullmatch(sha256):
            raise ValueError(
                f"Registry release sha256 must be 64 lowercase hex characters: {version}"
            )
        signature = _optional_release_string(raw, "signature")
        key_id = _optional_release_string(raw, "key-id")
        if (signature is None) != (key_id is None):
            raise ValueError(
                f"Registry release signature and key-id must appear together: {version}"
            )
        if key_id is not None:
            assert_slug(key_id, "Registry release key id")
        releases.append(
            RegistryReleaseRecord(
                registry=id_,
                version=version,
                archive=archive,
                sha256=sha256,
                signature=signature,
                key_id=key_id,
            )
        )
    releases.sort(key=lambda item: _version_parts(item.version), reverse=True)
    return RegistryIndexRecord(id=id_, name=name, source=source, releases=releases)


def select_registry_release(
    index: RegistryIndexRecord, version: str | None
) -> RegistryReleaseRecord:
    if version is None:
        return index.releases[0]
    validate_registry_version(version)
    for release in index.releases:
        if release.version == version:
            return release
    raise FileNotFoundError(f"Registry release not found: {index.id}@{version}")


def verify_release_signature(
    release: RegistryReleaseRecord,
    *,
    public_key: str | None,
    require_signature: bool,
    trusted_keys: list[RegistryTrustKeyRecord] | None = None,
) -> bool:
    if release.signature is None:
        if require_signature:
            raise ValueError(f"Registry release is unsigned: {release.registry}@{release.version}")
        return False
    matching_key = next(
        (
            item
            for item in trusted_keys or []
            if item.id == release.key_id and item.registry == release.registry
        ),
        None,
    )
    if matching_key is not None and matching_key.status == "revoked":
        raise PermissionError(
            f"Registry release key is revoked: {release.registry}/{matching_key.id}"
        )
    if public_key is None and matching_key is None:
        if require_signature:
            raise ValueError(f"No active trusted key found for {release.registry}/{release.key_id}")
        return False
    if public_key is not None:
        key_path = Path(public_key).expanduser().resolve()
        if not key_path.is_file():
            raise FileNotFoundError(f"Registry public key not found: {key_path}")
        loaded_key = load_pem_public_key(key_path.read_bytes())
        if not isinstance(loaded_key, Ed25519PublicKey):
            raise ValueError(f"Registry public key must be Ed25519: {key_path}")
    else:
        assert matching_key is not None
        loaded_key = Ed25519PublicKey.from_public_bytes(
            decode_trusted_public_key(matching_key.public_key)
        )
    try:
        signature = base64.b64decode(release.signature, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Registry release signature must be valid base64") from error
    try:
        loaded_key.verify(signature, release_signature_payload(release))
    except InvalidSignature as error:
        raise ValueError(
            f"Registry release signature is invalid: {release.registry}@{release.version}"
        ) from error
    return True


def release_signature_payload(release: RegistryReleaseRecord) -> bytes:
    return (
        f"{SIGNATURE_SCHEMA}\n"
        f"registry={release.registry}\n"
        f"version={release.version}\n"
        f"archive={release.archive}\n"
        f"sha256={release.sha256}\n"
    ).encode()


def validate_registry_version(value: str) -> str:
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"Registry version must use MAJOR.MINOR.PATCH: {value}")
    return value


def compare_registry_versions(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def _read_source(
    source: str,
    *,
    maximum: int,
    allow_insecure_http: bool,
    label: str,
) -> tuple[bytes, str]:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        _assert_url_transport(source, allow_insecure_http)
        request = Request(source, headers={"User-Agent": "agora-framework/0.2"})
        try:
            with urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                resolved = response.geturl()
                _assert_url_transport(resolved, allow_insecure_http)
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > maximum:
                    raise ValueError(f"Remote {label} exceeds {maximum} bytes")
                return _read_limited(response, maximum, label), resolved
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"Could not download {label} from {source}: {error}") from error
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path)).resolve()
    elif not parsed.scheme:
        path = Path(source).expanduser().resolve()
    else:
        raise ValueError(f"Unsupported registry source scheme: {parsed.scheme}")
    if not path.is_file():
        raise FileNotFoundError(f"Registry {label} not found: {path}")
    if path.stat().st_size > maximum:
        raise ValueError(f"Registry {label} exceeds {maximum} bytes")
    return path.read_bytes(), path.as_uri()


def _read_limited(stream: object, maximum: int, label: str) -> bytes:
    data = stream.read(maximum + 1)  # type: ignore[attr-defined]
    if len(data) > maximum:
        raise ValueError(f"Remote {label} exceeds {maximum} bytes")
    return data


def _assert_url_transport(url: str, allow_insecure_http: bool) -> None:
    scheme = urlparse(url).scheme
    if scheme == "https":
        return
    if scheme == "http" and allow_insecure_http:
        return
    if scheme == "http":
        raise PermissionError("HTTP registry sources require --allow-insecure-http")
    raise ValueError(f"Remote registry URL must use HTTPS: {url}")


def _resolve_archive_source(index_source: str, archive: str) -> str:
    parsed_archive = urlparse(archive)
    parsed_index = urlparse(index_source)
    if parsed_index.scheme in {"http", "https"}:
        if parsed_archive.scheme and parsed_archive.scheme not in {"http", "https"}:
            raise ValueError("Remote registry indexes cannot reference local archive sources")
        return urljoin(index_source, archive)
    if parsed_archive.scheme:
        return archive
    index_path = Path(unquote(parsed_index.path))
    return (index_path.parent / archive).resolve().as_uri()


def _extract_archive(contents: bytes, source: str, destination: Path) -> None:
    path = urlparse(source).path.lower()
    if path.endswith(".zip"):
        _extract_zip(contents, destination)
        return
    if path.endswith((".tar.gz", ".tgz")):
        _extract_tar(contents, destination)
        return
    raise ValueError("Registry archives must use .zip, .tar.gz, or .tgz")


def _extract_zip(contents: bytes, destination: Path) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            members = archive.infolist()
            _assert_member_count(members)
            total = 0
            seen: set[PurePosixPath] = set()
            for member in members:
                relative = _safe_member_path(member.filename, seen)
                if member.is_dir():
                    (destination / relative).mkdir(parents=True, exist_ok=True)
                    continue
                member_type = stat.S_IFMT(member.external_attr >> 16)
                if member_type not in {0, stat.S_IFREG}:
                    raise ValueError(
                        f"Registry archive contains a non-file entry: {member.filename}"
                    )
                total = _checked_total(total, member.file_size)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source_stream, target.open("wb") as target_stream:
                    _copy_member(source_stream, target_stream, member.file_size)
    except zipfile.BadZipFile as error:
        raise ValueError("Registry archive is not a valid zip file") from error


def _extract_tar(contents: bytes, destination: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(contents), mode="r:gz") as archive:
            members = archive.getmembers()
            _assert_member_count(members)
            total = 0
            seen: set[PurePosixPath] = set()
            for member in members:
                relative = _safe_member_path(member.name, seen)
                if member.isdir():
                    (destination / relative).mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ValueError(f"Registry archive contains a non-file entry: {member.name}")
                total = _checked_total(total, member.size)
                source_stream = archive.extractfile(member)
                if source_stream is None:
                    raise ValueError(f"Registry archive file cannot be read: {member.name}")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with source_stream, target.open("wb") as target_stream:
                    _copy_member(source_stream, target_stream, member.size)
    except tarfile.TarError as error:
        raise ValueError("Registry archive is not a valid gzip tar file") from error


def _safe_member_path(name: str, seen: set[PurePosixPath]) -> PurePosixPath:
    if not name or len(name) > MAX_ARCHIVE_PATH or "\\" in name or any(ord(c) < 32 for c in name):
        raise ValueError(f"Registry archive contains an unsafe path: {name!r}")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"Registry archive path escapes its destination: {name}")
    normalized = PurePosixPath(*[part for part in relative.parts if part not in {"", "."}])
    if str(normalized) == ".":
        raise ValueError(f"Registry archive contains an unsafe path: {name!r}")
    if normalized in seen:
        raise ValueError(f"Registry archive contains a duplicate path: {name}")
    seen.add(normalized)
    return normalized


def _assert_member_count(members: list[object]) -> None:
    if len(members) > MAX_ARCHIVE_FILES:
        raise ValueError(f"Registry archive exceeds {MAX_ARCHIVE_FILES} entries")


def _checked_total(current: int, size: int) -> int:
    if size < 0 or size > MAX_EXTRACTED_BYTES or current + size > MAX_EXTRACTED_BYTES:
        raise ValueError(f"Registry archive exceeds {MAX_EXTRACTED_BYTES} extracted bytes")
    return current + size


def _copy_member(source: object, destination: object, expected: int) -> None:
    remaining = expected
    while remaining:
        chunk = source.read(min(64 * 1024, remaining))  # type: ignore[attr-defined]
        if not chunk:
            raise ValueError("Registry archive member ended before its declared size")
        destination.write(chunk)  # type: ignore[attr-defined]
        remaining -= len(chunk)


def _find_registry_root(root: Path) -> Path:
    if (root / "REGISTRY.md").is_file():
        return root
    candidates = [path.parent for path in root.glob("*/REGISTRY.md") if path.is_file()]
    if len(candidates) != 1:
        raise ValueError("Registry archive must contain one REGISTRY.md at its root or first level")
    return candidates[0]


def _required_release_string(attributes: dict[object, object], key: str) -> str:
    value = attributes.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Registry release requires a non-empty {key}")
    return value


def _optional_release_string(attributes: dict[object, object], key: str) -> str | None:
    value = attributes.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Registry release {key} must be a non-empty string")
    return value


def _version_parts(value: str) -> tuple[int, int, int]:
    validate_registry_version(value)
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]
