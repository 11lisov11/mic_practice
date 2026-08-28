from dataclasses import replace

import numpy as np
import pytest
import torch

from config.env import create_default_env
from mic_ai.ai.train_ai_id_ref import _omega_base_from_env, _resolve_torch_device, _seed_all


def test_auto_device_resolves_to_available_backend() -> None:
    expected = "cuda" if torch.cuda.is_available() else "cpu"
    assert _resolve_torch_device("auto") == expected
    assert _resolve_torch_device("cpu") == "cpu"
    with pytest.raises(ValueError):
        _resolve_torch_device("tpu")


def test_explicit_cuda_never_silently_falls_back_to_cpu() -> None:
    if torch.cuda.is_available():
        assert _resolve_torch_device("cuda").startswith("cuda")
    else:
        with pytest.raises(RuntimeError):
            _resolve_torch_device("cuda")


def test_seed_contract_replays_numpy_and_torch() -> None:
    _seed_all(560225)
    first_np = np.random.uniform(size=4)
    first_torch = torch.rand(4)
    _seed_all(560225)
    assert np.array_equal(first_np, np.random.uniform(size=4))
    assert torch.equal(first_torch, torch.rand(4))


def test_speed_base_is_explicit_and_missing_value_fails_closed() -> None:
    env = create_default_env()
    assert _omega_base_from_env(env) == pytest.approx(env.omega_base_rad_s)
    with pytest.raises(ValueError):
        _omega_base_from_env(replace(env, omega_base_rad_s=None))
