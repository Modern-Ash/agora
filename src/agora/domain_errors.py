"""Typed failures raised where Agora Core applies domain rules."""


class DomainRuleError(ValueError):
    """A durable command violated a domain rule."""


class ProjectIdentityMismatchRuleError(DomainRuleError):
    pass


class StalePreconditionRuleError(DomainRuleError):
    pass


class GateAlreadyResolvedRuleError(DomainRuleError):
    pass


class EvidenceMissingRuleError(DomainRuleError):
    pass


class GateDecisionRoleRuleError(DomainRuleError):
    pass


class ActorUnauthorizedRuleError(PermissionError):
    pass


class SignatureRequiredRuleError(PermissionError):
    pass
