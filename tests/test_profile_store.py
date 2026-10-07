import pytest
from evdev import ecodes as e

from linmbc.profile import Action, Profile, load, save
from linmbc.profile_store import ProfileStore, slug


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Path of Exile 2", "path-of-exile-2"),
        ("Diablo IV: ção!", "diablo-iv-ção"),
        ("???", "profile"),
    ],
)
def test_slug(name, expected):
    assert slug(name) == expected


def test_list_reads_profiles_and_skips_broken(tmp_path):
    save(Profile(name="A"), tmp_path / "a.toml")
    (tmp_path / "broken.toml").write_text("name = ")
    store = ProfileStore(tmp_path)
    assert list(store.list()) == ["A"]


def test_save_new_profile_creates_file_from_name(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile(name="Last Epoch", buttons={e.BTN_SIDE: Action((e.KEY_1,))}))
    assert load(tmp_path / "last-epoch.toml").buttons == {e.BTN_SIDE: Action((e.KEY_1,))}


def test_save_does_not_overwrite_another_profile_with_same_slug(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile(name="Game"))
    store.save(Profile(name="game"))
    assert sorted(p.name for p in tmp_path.glob("*.toml")) == ["game-2.toml", "game.toml"]


def test_edit_keeps_file_and_rename_moves_name(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile(name="Old"))
    store.save(Profile(name="New", buttons={e.BTN_EXTRA: Action((e.KEY_E,))}), previous_name="Old")
    assert list(store.list()) == ["New"]
    assert [p.name for p in tmp_path.glob("*.toml")] == ["old.toml"]


def test_rename_onto_existing_name_is_refused(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile(name="A"))
    store.save(Profile(name="B"))
    with pytest.raises(ValueError, match="already exists"):
        store.save(Profile(name="A"), previous_name="B")
    with pytest.raises(ValueError, match="already exists"):
        store.save(Profile(name="A"))


def test_delete_removes_file(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile(name="A"))
    store.delete("A")
    assert list(store.list()) == []
    assert not list(tmp_path.glob("*.toml"))
