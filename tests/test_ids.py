"""id와 해시 만들기 (플랫폼 id 패턴, RFC 8785 정규화 해시)."""
import hashlib
import re

import pytest

from ocr_harness.common.ids import canonical_json, content_digest, manifest_digest
from ocr_harness.project import item_id

import samples

PLATFORM_ID = re.compile(r"^[a-z][a-z0-9.-]{1,63}$")


def test_item_id_is_a_platform_id_derived_from_image_digest():
    value = item_id("sha256:" + "ab" * 32)
    assert PLATFORM_ID.match(value)
    assert value == "img-" + "ab" * 16


def test_item_id_rejects_something_that_is_not_a_digest():
    with pytest.raises(ValueError):
        item_id("abc")


def test_canonical_json_follows_rfc_8785():
    # RFC 8785: 키 정렬, 공백 없음, 한글은 이스케이프하지 않고 UTF-8 그대로, 숫자는 ECMAScript 표기(1.0 → 1).
    assert canonical_json({"b": 1.0, "a": "한", "c": None, "d": [True, 1e21]}) == \
        '{"a":"한","b":1,"c":null,"d":[true,1e+21]}'.encode("utf-8")


def test_manifest_digest_ignores_key_order():
    manifest = samples.condition_manifest()
    reordered = dict(reversed(list(manifest.items())))
    assert manifest_digest(manifest) == manifest_digest(reordered)
    assert re.match(r"^sha256:[a-f0-9]{64}$", manifest_digest(manifest))


def test_manifest_digest_changes_when_any_setting_changes():
    manifest = samples.condition_manifest()
    changed = samples.condition_manifest()
    changed["components"]["retrieval"]["version"] = "1.0.1"
    assert manifest_digest(manifest) != manifest_digest(changed)


def test_content_digest_of_text_is_the_hash_of_its_utf8_bytes():
    assert content_digest("합성정") == "sha256:" + hashlib.sha256("합성정".encode("utf-8")).hexdigest()


def test_content_digest_of_structured_content_uses_canonical_json():
    messages = samples.raw_payload()["content"]
    assert content_digest(messages) == "sha256:" + hashlib.sha256(canonical_json(messages)).hexdigest()
