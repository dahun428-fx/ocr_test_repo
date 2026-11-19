"""라벨에서 필드를 뽑고 OCR 결과와 비교하는 규칙 (M1a 집계의 근거)."""
from ocr_harness.fields import Token, extract_fields, is_misread, norm


def poly(text, type_code, x, y, w=100, h=40):
    return {"id": "p", "type": type_code, "text": text,
            "points": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}


def label(*polygons):
    return {"images": [{"product_name": "합성정10mg 30정"}], "annotations": [{"polygons": list(polygons)}]}


def line(text, x, y, w=100, h=40):
    return Token(text, (x, y, x + w, y + h))


def test_norm_ignores_spacing_brackets_and_unit_spelling():
    assert norm("합성 정 10 밀리그램 (KP)") == norm("합성정10mg[kp]")


def test_product_name_field_joins_type1_words_and_drops_marks():
    fields = extract_fields(label(poly("합성", 1, 0, 0), poly("R", 1, 110, 0), poly("정", 1, 220, 0)))
    name = [f for f in fields if f.name == "product_name"][0]
    assert name.query_type == "B"
    assert [t.text for t in name.tokens] == ["합성", "정"]


def test_expiry_field_is_type_a_and_needs_a_date():
    fields = extract_fields(label(poly("사용기한", 3, 0, 0), poly("2027.01.31", 3, 110, 0)))
    expiry = [f for f in fields if f.name == "expiry"][0]
    assert expiry.query_type == "A"
    assert [t.text for t in expiry.tokens] == ["2027.01.31"]
    assert [f.name for f in extract_fields(label(poly("하단표시", 3, 0, 0)))] == []


def test_active_ingredient_field_is_words_between_marker_and_amount():
    fields = extract_fields(label(
        poly("유효성분", 2, 0, 0), poly("가상성분염(KP)", 2, 110, 0), poly("50mg", 2, 220, 0),
        poly("첨가제", 2, 0, 50), poly("유당", 2, 110, 50),
    ))
    active = [f for f in fields if f.name == "active_ingredient"][0]
    assert active.query_type == "B"
    assert [t.text for t in active.tokens] == ["가상성분염(KP)"]


def test_no_active_ingredient_field_without_marker():
    assert extract_fields(label(poly("유당", 2, 0, 0), poly("50mg", 2, 110, 0))) == []


def test_field_is_not_misread_when_overlapping_ocr_line_contains_each_word():
    field = extract_fields(label(poly("합성", 1, 0, 0), poly("정", 1, 110, 0)))[0]
    assert is_misread(field, [line("합성 정 10mg", 0, 0, w=400)]) is False


def test_field_is_misread_when_ocr_text_differs():
    field = extract_fields(label(poly("합성", 1, 0, 0)))[0]
    assert is_misread(field, [line("함성", 0, 0)]) is True


def test_field_is_misread_when_ocr_found_nothing_at_that_place():
    field = extract_fields(label(poly("합성", 1, 0, 0)))[0]
    assert is_misread(field, [line("합성", 1000, 1000)]) is True


def test_word_split_across_two_ocr_boxes_is_read_left_to_right():
    field = extract_fields(label(poly("가상성분", 1, 0, 0, w=200)))[0]
    assert is_misread(field, [line("성분", 100, 0), line("가상", 0, 0)]) is False


def test_ingredient_words_are_read_line_by_line_even_if_labelled_out_of_order():
    fields = extract_fields(label(
        poly("첨가제", 2, 0, 50), poly("50mg", 2, 220, 2), poly("가상성분염", 2, 110, 0),
        poly("유당", 2, 110, 52), poly("유효성분", 2, 0, 3),
    ))
    active = [f for f in fields if f.name == "active_ingredient"][0]
    assert [t.text for t in active.tokens] == ["가상성분염"]
