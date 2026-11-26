import pytest

from app.modules.workspaces import validation


def test_currency_and_timezone_lists():
    assert validation.validate_currency(" usd ") == "USD"
    assert validation.validate_timezone("Europe/Berlin") == "Europe/Berlin"
    for bad in ("XXX", "XAU", "ABC", "US"):
        with pytest.raises(ValueError):
            validation.validate_currency(bad)
    for bad in ("", "europe/berlin ", "Mars/Base", "../etc/passwd"):
        with pytest.raises(ValueError):
            validation.validate_timezone(bad)


@pytest.mark.parametrize("slug", ["abc", "my-home-2", "a1b"])
def test_valid_slugs(slug):
    assert validation.validate_slug(slug) == slug


@pytest.mark.parametrize("slug", ["ab", "-abc", "abc-", "a--b", "ABC", "a b", "x" * 49, "é-home"])
def test_invalid_slugs(slug):
    with pytest.raises(ValueError):
        validation.validate_slug(slug)


def test_slugify():
    assert validation.slugify("Our Home!") == "our-home"
    assert validation.slugify("Café Münch") == "cafe-munch"
    assert validation.slugify("日本語") == "workspace"
    assert len(validation.slugify("a" * 100)) <= validation.MAX_SLUG_LENGTH - 9
