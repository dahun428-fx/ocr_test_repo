"""id와 해시 만들기 (플랫폼 id 패턴, manifestDigest)."""
import re

from ocr_harness.ids import item_id, manifest_digest

import samples

PLATFORM_ID = re.compile(r"^[a-z][a-z0-9.-]{1,63}$")


def test_item_id_is_a_platform_id_derived_from_image_digest():
    value = item_id("sha256:" + "ab" * 32)
    assert PLATFORM_ID.match(value)
    assert value == "img-" + "ab" * 16


def test_item_id_rejects_something_that_is_not_a_digest():
    try:
        item_id("abc")
    except ValueError:
        return
    raise AssertionError("ValueError가 나야 합니다")


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
