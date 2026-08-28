import torch

from models.air56b2_id_policy import Air56B2IdPolicy, FEATURE_KEYS, IdPolicyScaling


def test_policy_shape_and_output_bounds() -> None:
    policy = Air56B2IdPolicy((16, 8))
    output = policy(torch.zeros((5, len(FEATURE_KEYS))))
    assert output.shape == (5,)
    assert torch.all(output >= 0.0)
    assert torch.all(output <= 1.0)


def test_policy_scaling_round_trip() -> None:
    scaling = IdPolicyScaling()
    for value in (scaling.id_lower_a, 0.8, scaling.id_upper_a):
        restored = scaling.denormalize_id(scaling.normalize_id(value))
        assert abs(restored - value) < 1e-12
    assert scaling.normalize_temperature(20.0) == 0.0
    assert scaling.normalize_temperature(160.0) == 1.0
