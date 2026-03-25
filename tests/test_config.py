import pytest
import yaml

from pdh_ng.config import REQUIRED_KEYS, Config, _env_var, load_and_validate


@pytest.fixture(autouse=True)
def reset_config():
    """Reset the module-level config singleton between tests."""
    from pdh_ng import config as config_module

    config_module.config.cfg = {}
    yield
    config_module.config.cfg = {}


@pytest.fixture
def valid_yaml(tmp_path):
    data = {"apikey": "key123", "uid": "U123", "email": "user@example.com"}
    f = tmp_path / "config.yaml"
    f.write_text(yaml.dump(data))
    return f, data


@pytest.fixture
def partial_yaml(tmp_path):
    data = {"apikey": "key123"}
    f = tmp_path / "config.yaml"
    f.write_text(yaml.dump(data))
    return f, data


class TestConfig:
    """Tests for the Config class dict interface."""

    def test_from_yaml(self, valid_yaml):
        path, data = valid_yaml
        cfg = Config()
        cfg.from_yaml(str(path))
        for k, v in data.items():
            assert cfg[k] == v

    def test_from_yaml_missing_file(self, tmp_path):
        cfg = Config()
        with pytest.raises(FileNotFoundError):
            cfg.from_yaml(str(tmp_path / "nonexistent.yaml"))

    def test_setitem_getitem(self):
        cfg = Config()
        cfg["apikey"] = "xyz"
        assert cfg["apikey"] == "xyz"

    def test_contains(self):
        cfg = Config()
        cfg["apikey"] = "abc"
        assert "apikey" in cfg
        assert "uid" not in cfg


class TestLoadAndValidate:
    """Tests for the load_and_validate function."""

    def test_valid_config_file(self, valid_yaml):
        path, data = valid_yaml
        cfg = load_and_validate(str(path))
        assert cfg["apikey"] == data["apikey"]
        assert cfg["uid"] == data["uid"]
        assert cfg["email"] == data["email"]

    def test_missing_file_with_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDH_NG_APIKEY", "envkey")
        monkeypatch.setenv("PDH_NG_UID", "envuid")
        monkeypatch.setenv("PDH_NG_EMAIL", "env@example.com")
        cfg = load_and_validate(str(tmp_path / "nonexistent.yaml"))
        assert cfg["apikey"] == "envkey"
        assert cfg["uid"] == "envuid"
        assert cfg["email"] == "env@example.com"

    def test_env_vars_fill_missing_keys(self, partial_yaml, monkeypatch):
        path, _ = partial_yaml
        monkeypatch.setenv("PDH_NG_UID", "envuid")
        monkeypatch.setenv("PDH_NG_EMAIL", "env@example.com")
        cfg = load_and_validate(str(path))
        assert cfg["apikey"] == "key123"
        assert cfg["uid"] == "envuid"
        assert cfg["email"] == "env@example.com"

    def test_env_vars_do_not_override_file(self, valid_yaml, monkeypatch):
        path, data = valid_yaml
        monkeypatch.setenv("PDH_NG_APIKEY", "envkey")
        cfg = load_and_validate(str(path))
        assert cfg["apikey"] == data["apikey"]

    def test_missing_file_no_env_vars_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            load_and_validate(str(tmp_path / "nonexistent.yaml"))

    def test_partial_file_missing_env_vars_exits(self, partial_yaml):
        path, _ = partial_yaml
        with pytest.raises(SystemExit):
            load_and_validate(str(path))

    def test_env_var_naming(self):
        assert _env_var("apikey") == "PDH_NG_APIKEY"
        assert _env_var("uid") == "PDH_NG_UID"
        assert _env_var("log_level") == "PDH_NG_LOG_LEVEL"

    def test_optional_key_overridable_via_env(self, valid_yaml, monkeypatch):
        path, _ = valid_yaml
        monkeypatch.setenv("PDH_NG_LOG_LEVEL", "WARNING")
        cfg = load_and_validate(str(path))
        assert cfg["log_level"] == "WARNING"

    def test_required_keys(self):
        assert set(REQUIRED_KEYS) == {"apikey", "uid", "email"}
