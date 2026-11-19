"""데이터 제품명 ↔ 공개 의약품 목록 매칭 규칙 (M1a (나))."""
from ocr_harness.kb_match import build_index, match

MFDS = ["합성정10밀리그램(가상성분염)", "합성정20밀리그램(가상성분염)", "다른캡슐", "모호액0.5%", "모호액0.5%(1회용)"]
INDEX = build_index(MFDS)


def test_exact_when_one_public_item_has_the_same_name_without_pack_size():
    assert match("합성정10mg(가상성분염) 30정", INDEX) == ("exact", ["합성정10밀리그램(가상성분염)"])


def test_exact_when_names_differ_only_by_ingredient_in_brackets():
    assert match("합성정20mg 100정", INDEX) == ("exact", ["합성정20밀리그램(가상성분염)"])


def test_pack_size_with_multiplier_is_ignored():
    assert match("다른캡슐 10캡슐 x 3", INDEX)[0] == "exact"


def test_ambiguous_when_only_a_prefix_matches_several_items():
    kind, names = match("합성정", INDEX)
    assert kind == "ambiguous" and len(names) == 2


def test_full_name_match_wins_over_items_sharing_the_base_name():
    assert match("모호액0.5% 5ml", INDEX) == ("exact", ["모호액0.5%"])


def test_ambiguous_when_two_items_share_the_base_name():
    kind, names = match("모호액0.5%(가상성분) 5ml", INDEX)
    assert kind == "ambiguous" and len(names) == 2


def test_unmatched_when_nothing_is_close():
    assert match("없는연고 10g", INDEX) == ("unmatched", [])
