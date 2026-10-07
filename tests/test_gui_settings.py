from linmbc.gui.settings import GuiSettings, load_settings, ordered, save_settings


def test_round_trip(tmp_path):
    path = tmp_path / "gui.toml"
    settings = GuiSettings(language="pt_BR", profile_order=("PoE2", 'Last "Epoch"'))
    save_settings(settings, path)
    assert load_settings(path) == settings


def test_bad_file_gives_defaults(tmp_path):
    path = tmp_path / "gui.toml"
    path.write_text('language = 3\nprofile_order = "x"\n')
    assert load_settings(path) == GuiSettings()


def test_ordered_puts_unknown_names_last_in_their_order():
    assert ordered(["A", "B", "C", "D"], ("C", "A", "gone")) == ["C", "A", "B", "D"]
