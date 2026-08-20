import pytest

from agora.application import (
    AgoraApplicationError,
    AuthorityDeniedError,
    DurableStateInvalidError,
    GateEvidenceMissingError,
    GovernedMaterialStaleError,
    LifecyclePreconditionFailedError,
    PreparationExpiredError,
    ProviderExecutionFailedError,
    ResourceNotFoundError,
    RuntimeIncompatibleError,
    SignatureInvalidError,
    TransactionCommitError,
    TransactionIndeterminateError,
    TransactionRollbackError,
)


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (DurableStateInvalidError, "durable-state.invalid"),
        (ResourceNotFoundError, "resource.not-found"),
        (AuthorityDeniedError, "authority.denied"),
        (LifecyclePreconditionFailedError, "lifecycle.precondition-failed"),
        (GateEvidenceMissingError, "gate.evidence-missing"),
        (GovernedMaterialStaleError, "command.governed-material-stale"),
        (PreparationExpiredError, "command.preparation-expired"),
        (SignatureInvalidError, "command.signature-invalid"),
        (TransactionCommitError, "transaction.commit-failed"),
        (TransactionRollbackError, "transaction.rollback-failed"),
        (TransactionIndeterminateError, "transaction.indeterminate"),
        (RuntimeIncompatibleError, "runtime.incompatible"),
        (ProviderExecutionFailedError, "provider.execution-failed"),
    ],
)
def test_public_error_taxonomy_is_stable_and_serializable(
    error_type: type[AgoraApplicationError], code: str
) -> None:
    error = error_type("Safe human message")
    payload = error.to_dict()

    assert payload["schema"] == "agora/application/error/v2"
    assert payload["code"] == code
    assert isinstance(payload["category"], str)
    assert isinstance(payload["retryable"], bool)
    assert payload["message"] == "Safe human message"
    assert set(payload) == {
        "schema",
        "code",
        "message",
        "category",
        "retryable",
        "durable_path",
        "recovery_hint",
        "details",
    }


def test_error_details_redact_authentication_and_credentials_recursively() -> None:
    error = GovernedMaterialStaleError(
        "Material changed",
        details={
            "stale_reason": "actor-key-changed",
            "signature": "complete-signature",
            "nested": {
                "access-token": "secret-token",
                "credential": "password",
                "safe": ["one", 2],
            },
        },
    )

    assert error.to_dict()["details"] == {
        "stale_reason": "actor-key-changed",
        "signature": "[redacted]",
        "nested": {
            "access-token": "[redacted]",
            "credential": "[redacted]",
            "safe": ["one", 2],
        },
    }
