"""Typed failures raised where Agora Core applies domain rules."""


class DomainRuleError(ValueError):
    """A durable command violated a domain rule."""


class ProjectIdentityMismatchRuleError(DomainRuleError):
    pass


class StalePreconditionRuleError(DomainRuleError):
    def __init__(self, message: str, *, stale_reason: str = "governed-material-changed") -> None:
        super().__init__(message)
        self.stale_reason = stale_reason


class GovernedMaterialStaleRuleError(StalePreconditionRuleError):
    pass


class PreparationExpiredRuleError(StalePreconditionRuleError):
    def __init__(self, message: str) -> None:
        super().__init__(message, stale_reason="preparation-expired")


class GateAlreadyResolvedRuleError(DomainRuleError):
    pass


class EvidenceMissingRuleError(DomainRuleError):
    pass


class GateDecisionRoleRuleError(DomainRuleError):
    pass


class ActorUnauthorizedRuleError(PermissionError):
    pass


class SignatureInvalidRuleError(ActorUnauthorizedRuleError):
    pass


class SignatureRequiredRuleError(PermissionError):
    pass
