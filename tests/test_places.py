"""Fixed place list and "affects" tags (spec §5.10): loading the lists and checking the AI's choice."""

import re

import pytest

from haven.config import ConfigError, Place, load_places, load_tags
from haven.places import MAX_TAGS, SHEET_BBOX, Pick, pick


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


ONE_PLACE = """
[[place]]
id = "ect-delta"
label = "ECT Delta"
kind = "terminal"
lat = 51.9543
lon = 4.0293
side = "right"
osm = "way/145614140"
"""

# A small, made-up pair of lists for the validator tests (the real ones are tested below).
PLACES = (
    Place(id="ect-delta", label="ECT Delta", kind="terminal", lat=51.9543, lon=4.0293, side="right", osm="way/145614140"),
    Place(id="botlek", label="Botlek", kind="area", lat=51.8758, lon=4.2618, side="left", osm="node/5312148539"),
)
TAGS = ("Containers", "Barge", "Rail", "Rhine", "Truck pickups", "Hinterland", "Customs")


def choose(place, tags):
    return pick(place, tags, places=PLACES, tags_list=TAGS)


# ---------- The validator: the AI picks, the code fills in the facts ----------

def test_known_place_gets_coordinates_label_and_side_from_the_list():
    result = choose("ect-delta", ["Containers"])
    assert result.map == {"lat": 51.9543, "lon": 4.0293, "label": "ECT Delta", "side": "right"}
    assert result.unlisted is None


def test_none_means_no_pin_and_nothing_is_logged():
    for value in ("none", "None", "", None):
        result = choose(value, ["Barge"])
        assert result.map is None
        assert result.unlisted is None


def test_unknown_place_is_discarded_and_logged():
    result = choose("Calandkanaal", ["Barge"])
    assert result.map is None
    assert result.unlisted == {"places": ["Calandkanaal"], "tags": []}


def test_place_id_ignores_case_and_spaces_around_it():
    assert choose("  ECT-Delta ", []).map["label"] == "ECT Delta"


def test_mixed_tags_keep_the_listed_ones_and_log_the_rest():
    result = choose("none", ["Containers", "Reefers", "rail", "Cold chain"])
    assert result.affects == ["Containers", "Rail"]  # list spelling, not the AI's
    assert result.unlisted == {"places": [], "tags": ["Reefers", "Cold chain"]}


def test_place_labels_are_valid_location_tags():
    result = choose("none", ["Botlek", "Barge"])
    assert result.affects == ["Botlek", "Barge"]
    assert result.unlisted is None


def test_more_than_five_tags_keeps_the_first_five():
    result = choose("none", ["Containers", "Barge", "Rail", "Rhine", "Truck pickups", "Hinterland", "Customs"])
    assert len(result.affects) == MAX_TAGS == 5
    assert result.affects == ["Containers", "Barge", "Rail", "Rhine", "Truck pickups"]
    assert result.unlisted is None  # listed tags past the fifth are dropped, not "unlisted"


def test_unlisted_tags_do_not_use_up_the_five_places():
    result = choose("none", ["Reefers", "Containers", "Barge", "Rail", "Rhine", "Customs"])
    assert result.affects == ["Containers", "Barge", "Rail", "Rhine", "Customs"]
    assert result.unlisted == {"places": [], "tags": ["Reefers"]}


def test_duplicate_tags_count_once():
    assert choose("none", ["Barge", "barge", " Barge "]).affects == ["Barge"]


def test_place_label_is_added_as_a_tag_when_there_is_room():
    assert choose("botlek", ["Barge"]).affects == ["Barge", "Botlek"]
    assert choose("botlek", ["Botlek", "Barge"]).affects == ["Botlek", "Barge"]  # not twice
    full = ["Containers", "Barge", "Rail", "Rhine", "Customs"]
    assert choose("botlek", full).affects == full  # never more than five


def test_empty_or_missing_tags():
    assert choose("none", []).affects == []
    assert choose("none", None).affects == []


def test_non_text_answers_are_logged_not_crashed_on():
    result = choose(42, ["Barge", 7])
    assert result.map is None
    assert result.affects == ["Barge"]
    assert result.unlisted == {"places": ["42"], "tags": ["7"]}


def test_validator_never_outputs_anything_that_is_not_listed():
    allowed = set(TAGS) | {p.label for p in PLACES}
    for place in ("ect-delta", "botlek", "nowhere", "none"):
        result = choose(place, ["Containers", "Reefers", "BOTLEK", "Maasvlakte II", "rhine", "", "  "])
        assert set(result.affects) <= allowed
        assert result.map is None or result.map["label"] in {p.label for p in PLACES}


def test_record_fields_for_the_item():
    result = choose("Calandkanaal", ["Reefers", "Barge"])
    assert result.record() == {"map": None, "affects": ["Barge"],
                               "unlisted": {"places": ["Calandkanaal"], "tags": ["Reefers"]}}
    assert "unlisted" not in choose("botlek", ["Barge"]).record()


def test_pick_reads_the_real_lists_by_default():
    result = pick("ect-delta", ["Containers"])
    assert isinstance(result, Pick)
    assert result.map["label"] == "ECT Delta"


# ---------- Loading config/places.toml ----------

def test_place_is_loaded(tmp_path):
    (place,) = load_places(write(tmp_path, "places.toml", ONE_PLACE))
    assert place == PLACES[0]


@pytest.mark.parametrize("change, message", [
    (('kind = "terminal"', 'kind = "berth"'), "unknown kind 'berth'"),
    (('side = "right"', 'side = "up"'), "side 'up'"),
    (('osm = "way/145614140"', 'osm = "145614140"'), "osm"),
    (('lat = 51.9543', 'lat = 52.5'), "outside the chart sheet"),
    (('lon = 4.0293', 'lon = "4.0293"'), "'lon' must be a number"),
    (('id = "ect-delta"', 'id = "ECT Delta"'), "id"),
    (('id = "ect-delta"', 'id = "none"'), "'none'"),
    (('label = "ECT Delta"', 'label = " "'), "'label'"),
])
def test_bad_place_is_rejected(tmp_path, change, message):
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_places(write(tmp_path, "places.toml", ONE_PLACE.replace(*change)))


def test_missing_field_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="missing 'osm'"):
        load_places(write(tmp_path, "places.toml", ONE_PLACE.replace('osm = "way/145614140"\n', "")))


def test_unknown_field_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown field 'lng'"):
        load_places(write(tmp_path, "places.toml", ONE_PLACE + "lng = 4.0\n"))


def test_duplicate_id_or_label_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="duplicate id 'ect-delta'"):
        load_places(write(tmp_path, "places.toml", ONE_PLACE + ONE_PLACE))
    twin = ONE_PLACE + ONE_PLACE.replace('id = "ect-delta"', 'id = "ect-delta-2"')
    with pytest.raises(ConfigError, match="duplicate label 'ECT Delta'"):
        load_places(write(tmp_path, "places.toml", twin))


# ---------- Loading config/tags.toml ----------

def test_tags_are_loaded(tmp_path):
    assert load_tags(write(tmp_path, "tags.toml", 'affects = ["Containers", "Barge"]\n')) == ("Containers", "Barge")


@pytest.mark.parametrize("text, message", [
    ('affects = "Containers"\n', "list of tags"),
    ('affects = ["Containers", " "]\n', "empty tag"),
    ('affects = ["Barge", "barge"]\n', "duplicate tag 'barge'"),
    ('affect = ["Barge"]\n', "unknown key 'affect'"),
    ("# nothing\n", "missing 'affects'"),
])
def test_bad_tags_are_rejected(tmp_path, text, message):
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_tags(write(tmp_path, "tags.toml", text))


# ---------- The real lists in config/ ----------

def test_real_place_list_size_and_osm_ids():
    places = load_places()
    assert 30 <= len(places) <= 40
    for place in places:
        assert re.fullmatch(r"(node|way|relation)/\d+", place.osm), place.id


def test_every_real_place_lies_inside_the_chart_sheet():
    south, west, north, east = SHEET_BBOX
    assert SHEET_BBOX == (51.74, 3.40, 52.16, 4.62)  # spec §8.1
    for place in load_places():
        assert south <= place.lat <= north and west <= place.lon <= east, place.id


def test_real_lists_cover_every_kind_and_about_fifteen_tags():
    assert {p.kind for p in load_places()} >= {"terminal", "area", "anchorage", "lock", "fairway"}
    tags = load_tags()
    assert 12 <= len(tags) <= 18
    assert {"Containers", "Dry bulk", "Liquid bulk", "Barge", "Rail", "Truck pickups", "Rhine"} <= set(tags)


def test_no_tag_has_the_same_name_as_a_place():
    labels = {p.label.casefold() for p in load_places()}
    assert not labels & {t.casefold() for t in load_tags()}
