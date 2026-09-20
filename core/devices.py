"""Turn the user's device preference into what each library expects."""
from __future__ import annotations


def resolve_torch_device(pref: str) -> tuple[str | None, str | None]:
    """Return ``(device or None for auto, warning or None)`` for PyTorch-based engines."""
    if pref == "auto":
        return None, None
    if pref == "cpu":
        return "cpu", None
    try:
        import torch
    except ImportError:
        return "cpu", "PyTorch isn't installed; using CPU."
    if pref == "cuda":
        if torch.cuda.is_available():
            return "cuda", None
        return "cpu", "CUDA isn't available in this PyTorch install; using CPU."
    if pref == "mps":
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps", None
        return "cpu", "MPS isn't available here; using CPU."
    return None, None


def resolve_paddle_device(pref: str) -> tuple[str | None, str | None]:
    """Return ``(device or None for auto, warning or None)`` for PaddlePaddle."""
    if pref == "auto":
        return None, None
    if pref == "cpu":
        return "cpu", None
    if pref == "cuda":
        try:
            import paddle
            if paddle.device.is_compiled_with_cuda():
                return "gpu:0", None
        except ImportError:
            pass
        return "cpu", "This PaddlePaddle build has no CUDA support (needs paddlepaddle-gpu); using CPU."
    return "cpu", "PaddlePaddle doesn't support MPS; using CPU."
