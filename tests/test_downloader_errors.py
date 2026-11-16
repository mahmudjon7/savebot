"""yt-dlp error messages are mapped to the right user-facing error class."""

import pytest

from app.services.downloader import (
    DownloadFailedError,
    PrivateOrLoginRequiredError,
    VideoTooLargeError,
    _classify_yt_dlp_error,
)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("ERROR: [Instagram] X: This content isn't available to everyone: It can't be seen by certain audiences.",
         PrivateOrLoginRequiredError),
        ("ERROR: [Instagram] X: login required to view this", PrivateOrLoginRequiredError),
        ("ERROR: This video is private", PrivateOrLoginRequiredError),
        ("ERROR: Maximum file size exceeded", VideoTooLargeError),
        ("ERROR: something unexpected", DownloadFailedError),
    ],
)
def test_classify(message, expected):
    assert type(_classify_yt_dlp_error(message)) is expected
