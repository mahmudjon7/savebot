"""Tests for the content policy filter and its yt-dlp integration."""

import http.server
import socketserver
import threading

import pytest

from app.services.content_filter import (
    ADULT,
    AGE_RESTRICTED,
    CUSTOMS,
    OTHER_RELIGION,
    ContentFilter,
    load_extra_terms,
    normalize,
)

F = ContentFilter()


def blocked(info=None, text=None):
    v = F.check_info(info) if info is not None else F.check_text(text)
    return v.category if v.blocked else None


def test_age_limit() -> None:
    assert blocked({"title": "Cooking pasta", "age_limit": 18}) == AGE_RESTRICTED
    assert blocked({"title": "Cooking pasta", "age_limit": 0}) is None
    assert blocked({"title": "Cooking pasta"}) is None  # field missing (early extraction stage)


@pytest.mark.parametrize("title", [
    "Hot PORN compilation", "порно видео", "Yalang'och qiz", "yalangoch qizlar", "Ялангоч", "sexy dance 2024",
    "NSFW clip", "Эротика для взрослых", "xxx", "18+ only",
])
def test_adult_titles_blocked(title) -> None:
    assert blocked({"title": title}) == ADULT


@pytest.mark.parametrize("title", [
    "Essex travel vlog", "Middlesex University tour", "Sussex weather", "Plovni qanday pishiramiz",
    "Футбол: лучшие голы", "Churchill speech 1940", "Christian Bale interview", "Toshkent metro 2024",
    "How to cook beef, 18 minutes", "sexton chess lesson",
])
def test_innocent_titles_pass(title) -> None:
    assert blocked({"title": title}) is None


def test_other_religion_in_title_tags_channel() -> None:
    assert blocked({"title": "Sunday church service"}) == OTHER_RELIGION
    assert blocked({"title": "Hello", "tags": ["music", "Христианство"]}) == OTHER_RELIGION
    assert blocked({"title": "Hello", "uploader": "Cherkov TV"}) == OTHER_RELIGION
    assert blocked({"title": "Bible study"}) == OTHER_RELIGION


def test_description_needs_two_distinct_hits_for_religion() -> None:
    one = {"title": "City tour", "description": "We passed a church on the way."}
    two = {"title": "City tour", "description": "We passed a church and a synagogue."}
    assert blocked(one) is None
    assert blocked(two) == OTHER_RELIGION


def test_description_one_hit_is_enough_for_adult() -> None:
    assert blocked({"title": "Hello", "description": "full porn video inside"}) == ADULT


def test_customs_category() -> None:
    assert blocked({"title": "1xbet promo kod"}) == CUSTOMS
    assert blocked({"title": "Kazino o'yini"}) == CUSTOMS
    assert blocked({"title": "LGBT parade highlights"}) == CUSTOMS


def test_islamic_content_not_blocked() -> None:
    for t in ["Juma va'zi", "Quron tilovati", "Namoz o'qish tartibi", "Hajj 2024", "Ramazon duosi", "Шайтон васвасаси"]:
        assert blocked({"title": t, "description": "Islomiy ma'ruza"}) is None, t


def test_message_text_and_url_words() -> None:
    assert blocked(text="mana bu porno video https://x.com/a/status/1") == ADULT
    assert blocked(text="https://example.com/watch/porn-video-123") == ADULT
    assert blocked(text="https://youtu.be/dQw4w9WgXcQ salom") is None


def test_normalization_of_apostrophes() -> None:
    assert normalize("O‘zbek yalangʻoch") == "o'zbek yalang'och"
    assert blocked({"title": "yalangʻoch"}) == ADULT   # ʻ variant


def test_categories_can_be_disabled() -> None:
    only_adult = ContentFilter(categories=[ADULT])
    assert only_adult.check_info({"title": "church service", "age_limit": 18}).blocked is False
    assert only_adult.check_info({"title": "porn"}).blocked is True


def test_extra_terms_file(tmp_path) -> None:
    f = tmp_path / "terms.txt"
    f.write_text("# my terms\ncustoms|alkogol*\nbogus|zzz\nbad line\n adult | testword \n", encoding="utf-8")
    assert load_extra_terms(str(f)) == {"customs": ["alkogol*"], "adult": ["testword"]}
    flt = ContentFilter(extra_terms_file=str(f))
    assert flt.check_info({"title": "Alkogolli ichimlik"}).category == CUSTOMS
    assert flt.check_info({"title": "a testword here"}).category == ADULT
    assert load_extra_terms(str(tmp_path / "missing.txt")) == {}


def test_verdict_has_reason_for_logs() -> None:
    v = F.check_info({"title": "nice porn clip"})
    assert (v.blocked, v.category, v.source) == (True, ADULT, "title")
    assert v.term == "porn"


# ---- integration with real yt-dlp (generic extractor on a local HTTP server) --------------------

yt_dlp = pytest.importorskip("yt_dlp")


@pytest.fixture()
def media_server(tmp_path):
    (tmp_path / "porn-video.mp4").write_bytes(b"\x00" * 2048)
    (tmp_path / "cooking-pasta.mp4").write_bytes(b"\x00" * 2048)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(tmp_path), **kw)

        def log_message(self, *a):  # keep test output quiet
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_ytdlp_blocks_before_download(media_server, tmp_path) -> None:
    from app.services.downloader import ContentBlockedError, _sync_download_video

    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ContentBlockedError) as exc:
        _sync_download_video(f"{media_server}/porn-video.mp4", str(out), 50, 600, 30, content_check=F.check_info)
    assert exc.value.category == ADULT
    assert list(out.iterdir()) == []  # nothing was downloaded


def test_ytdlp_allows_clean_video(media_server, tmp_path) -> None:
    from app.services.downloader import _sync_download_video

    out = tmp_path / "out"
    out.mkdir()
    res = _sync_download_video(f"{media_server}/cooking-pasta.mp4", str(out), 50, 600, 30, content_check=F.check_info)
    assert res.file_path.endswith(".mp4")
