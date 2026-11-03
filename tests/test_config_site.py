"""Loading config/site.toml: the site's own addresses and its social preview image (spec §2.3, issue #28).

The base URL, the LinkedIn and repository links and the preview image's file name live in one
config file, read by the renderer (footer, "How it works", Today, social preview tags) and by
the fetcher (the user agent links "How it works").
"""

import json
import struct
import zlib

import pytest

from haven.config import ConfigError, SiteConfig, load_site, preview_image_size

GOOD = """
base_url = "https://example.github.io/haven-daily/"
linkedin_url = "https://www.linkedin.com/in/someone"
repo_url = "https://github.com/someone/haven-daily"
social_image = "social-preview.png"
social_image_alt = "A dark chart of a seaport at dusk."
"""


def write(tmp_path, text):
    path = tmp_path / "site.toml"
    path.write_text(text, encoding="utf-8")
    return path


def png(path, width, height):
    """A tiny valid PNG of the given size (one grey row repeated), written to `path`."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return path


def test_the_repo_file_has_the_sites_addresses():
    site = load_site()
    assert site == SiteConfig(
        base_url="https://leonardoneirotti.github.io/haven-daily/",
        linkedin_url="https://www.linkedin.com/in/leonardo-neirotti",
        repo_url="https://github.com/leonardoneirotti/haven-daily",
        social_image="social-preview.png",
        social_image_alt="A dark, stylised chart of a large seaport at dusk, with a few ships seen from above.",
    )


def test_a_good_file_loads(tmp_path):
    assert load_site(write(tmp_path, GOOD)).base_url == "https://example.github.io/haven-daily/"


@pytest.mark.parametrize("field", ["base_url", "linkedin_url", "repo_url", "social_image", "social_image_alt"])
def test_every_field_is_required(tmp_path, field):
    text = "\n".join(line for line in GOOD.splitlines() if not line.startswith(field + " "))
    with pytest.raises(ConfigError, match=rf"site.toml: missing {field!r}"):
        load_site(write(tmp_path, text))


def test_an_unknown_field_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="unknown field 'base_ulr'"):
        load_site(write(tmp_path, GOOD + 'base_ulr = "https://x.example/"\n'))


@pytest.mark.parametrize("field", ["base_url", "linkedin_url", "repo_url"])
@pytest.mark.parametrize("bad", ["http://example.org/", "example.org", "", "https://", "https://exa mple.org/"])
def test_addresses_must_be_https_web_addresses(tmp_path, field, bad):
    text = GOOD.replace(next(line for line in GOOD.splitlines() if line.startswith(field)), f'{field} = "{bad}"')
    with pytest.raises(ConfigError, match=rf"site.toml: {field} must be"):
        load_site(write(tmp_path, text))


def test_the_base_url_ends_with_a_slash(tmp_path):
    # Page addresses are the base URL + "days/2026-10-29.html": without the slash they'd break.
    with pytest.raises(ConfigError, match="base_url must end with /"):
        load_site(write(tmp_path, GOOD.replace("haven-daily/\"", "haven-daily\"")))


@pytest.mark.parametrize("bad", ["../secret.png", "images/x.png", "social-preview.jpg", "social preview.png", ""])
def test_the_social_image_is_a_png_file_name_in_static(tmp_path, bad):
    with pytest.raises(ConfigError, match="social_image must be"):
        load_site(write(tmp_path, GOOD.replace('"social-preview.png"', f'"{bad}"')))


@pytest.mark.parametrize("bad", ["", "   ", "two\nlines"])
def test_the_alt_text_is_one_line_of_text(tmp_path, bad):
    with pytest.raises(ConfigError, match="social_image_alt must be one line of text"):
        load_site(write(tmp_path, GOOD.replace('"A dark chart of a seaport at dusk."', json.dumps(bad))))


# ---------- The preview image's size: read from the PNG itself (no Pillow) ----------

def test_the_preview_image_size_is_read_from_the_png(tmp_path):
    assert preview_image_size(png(tmp_path / "a.png", 1200, 630)) == (1200, 630)


def test_the_preview_image_in_the_repo_is_1200_by_630_once_it_exists():
    # Not made yet (owner's checklist #43). When it is added to static/, it must be the size
    # LinkedIn shows uncropped; the renderer would leave a wrong-sized one out (test_social_tags).
    from pathlib import Path
    image = Path(__file__).resolve().parent.parent / "static" / load_site().social_image
    if image.exists():
        assert preview_image_size(image) == (1200, 630)


def test_a_file_that_is_not_a_png_has_no_size(tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"GIF89a not a png")
    assert preview_image_size(path) is None
