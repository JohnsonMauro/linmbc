from linmbc.games import Game, installed_steam_games, parse_vdf

LIBRARYFOLDERS = """
"libraryfolders"
{
\t"0"
\t{
\t\t"path"\t\t"{main}"
\t\t"apps" { "899770" "123" }
\t}
\t"1"
\t{
\t\t"path"\t\t"{extra}"
\t}
}
"""


def manifest(appid, name):
    return f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n}}\n'


def make_library(root, games):
    apps = root / "steamapps"
    apps.mkdir(parents=True)
    for appid, name in games:
        (apps / f"appmanifest_{appid}.acf").write_text(manifest(appid, name))
    return apps


def test_parse_vdf_nested_and_escaped():
    data = parse_vdf('"a" { "b" "c \\"q\\"" "d" { "e" "f" } }')
    assert data == {"a": {"b": 'c "q"', "d": {"e": "f"}}}


def test_lists_games_from_every_library_and_skips_tools(tmp_path):
    main = tmp_path / "Steam"
    extra = tmp_path / "SSD" / "SteamLibrary"
    apps = make_library(
        main,
        [
            ("899770", "Last Epoch"),
            ("1493710", "Proton Experimental"),
            ("4183110", "Steam Linux Runtime 4.0"),
            ("228980", "Steamworks Common Redistributables"),
        ],
    )
    make_library(extra, [("2694490", "Path of Exile 2")])
    (apps / "libraryfolders.vdf").write_text(
        LIBRARYFOLDERS.replace("{main}", str(main)).replace("{extra}", str(extra))
    )

    games = installed_steam_games([main])

    assert games == [
        Game("Last Epoch", ("steam_app_899770",)),
        Game("Path of Exile 2", ("steam_app_2694490",)),
    ]


def test_same_library_reached_through_a_symlink_is_listed_once(tmp_path):
    main = tmp_path / "Steam"
    apps = make_library(main, [("899770", "Last Epoch")])
    (apps / "libraryfolders.vdf").write_text(
        LIBRARYFOLDERS.replace("{main}", str(main)).replace("{extra}", str(main))
    )
    link = tmp_path / "steam-link"
    link.symlink_to(main)
    assert len(installed_steam_games([main, link])) == 1


def test_missing_or_broken_files_give_an_empty_list(tmp_path):
    assert installed_steam_games([tmp_path / "nope"]) == []
    apps = make_library(tmp_path / "Steam", [])
    (apps / "libraryfolders.vdf").write_text('"libraryfolders" {')
    (apps / "appmanifest_1.acf").write_text("garbage")
    assert installed_steam_games([tmp_path / "Steam"]) == []


def test_parse_vdf_keeps_non_ascii_names():
    assert parse_vdf('"name" "Pokémon \\\\ ção"') == {"name": "Pokémon \\ ção"}
