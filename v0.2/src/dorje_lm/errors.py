"""LM abstraction errors."""


class LMError(RuntimeError):
    """Base class for LM errors."""


class LMConfigError(LMError):
    """Invalid LM configuration."""


class LMProviderError(LMError):
    """Provider-side LM failure."""


class LMSidecarError(LMProviderError):
    """Pi sidecar process failure."""
