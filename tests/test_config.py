from linmbc.config import Config, load_config, save_config


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "none.toml") == Config()


def test_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    config = Config(enabled=True, default_profile='A "q"')
    save_config(config, path)
    assert load_config(path) == config


def test_corrupt_file_falls_back_to_disabled_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("enabled = ")
    assert load_config(path) == Config()


def test_wrong_types_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('enabled = "yes"\ndefault_profile = 3\n')
    assert load_config(path) == Config()


def test_keys_from_older_versions_are_ignored(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('enabled = true\ndevices = ["x"]\nactive_profile = "Last Epoch"\n')
    assert load_config(path) == Config(enabled=True)
