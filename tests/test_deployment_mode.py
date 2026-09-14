from deployment_mode import allow_admin_controls, is_shared_mode


def test_shared_mode_parses_only_explicit_truthy_values():
    assert all(is_shared_mode(v) for v in [True, "true", "1", "YES", "on"])
    assert not any(is_shared_mode(v) for v in [False, None, "", "false", "0", "random"])


def test_shared_mode_never_exposes_admin_controls():
    assert allow_admin_controls(shared=True, raw_exists=True) is False
    assert allow_admin_controls(shared=False, raw_exists=True) is True
    assert allow_admin_controls(shared=False, raw_exists=False) is False
