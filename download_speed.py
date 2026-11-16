"""Measure HTTP download speed with ten sequential GET requests."""

import argparse
import sys
from http import HTTPStatus
from http.client import HTTPException
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 3600


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_url(value):
    try:
        parts = urlsplit(value)
        if parts.scheme in {"http", "https"} and parts.hostname:
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected an http:// or https:// URL")


def positive_seconds(value):
    try:
        seconds = float(value)
    except ValueError:
        seconds = 0
    if not 0 < seconds <= MAX_TIMEOUT:
        raise argparse.ArgumentTypeError(f"expected seconds greater than 0 and at most {MAX_TIMEOUT}")
    return seconds


def expected_body_size(response):
    encodings = response.headers.get_all("Transfer-Encoding", [])
    lengths = response.headers.get_all("Content-Length", [])
    if encodings:
        if [value.lower() for value in encodings] != ["chunked"] or lengths:
            raise HTTPException("unsupported or ambiguous Transfer-Encoding")
        return None
    if not lengths:
        return None
    if len(lengths) != 1 or not (lengths[0].isascii() and lengths[0].isdecimal()):
        raise HTTPException("invalid or ambiguous Content-Length")
    return int(lengths[0])


def download(opener, url, timeout):
    request = Request(url, headers={"Accept-Encoding": "identity"})
    start = perf_counter()
    with opener.open(request, timeout=timeout) as response:
        if response.status == HTTPStatus.PARTIAL_CONTENT:
            raise HTTPException("HTTP 206 Partial Content: expected a full response")
        expected_size = expected_body_size(response)
        size = 0
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)

        # A bounded read can return EOF without raising on a short body.
        if expected_size is not None and size != expected_size:
            raise HTTPException(f"incomplete response: got {size} of {expected_size} bytes")
    return size, perf_counter() - start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", type=http_url, help="direct URL of a downloadable file")
    parser.add_argument(
        "--timeout",
        type=positive_seconds,
        default=DEFAULT_TIMEOUT,
        help=f"socket timeout in seconds, up to {MAX_TIMEOUT} (default: %(default)s)",
    )
    args = parser.parse_args()
    opener = build_opener(NoRedirects())
    total_bytes = 0
    total_seconds = 0.0

    for number in range(1, REQUEST_COUNT + 1):
        try:
            size, elapsed = download(opener, args.url, args.timeout)
        except HTTPError as error:
            error.close()
            print(f"Request {number}/{REQUEST_COUNT} failed: HTTP {error.code}", file=sys.stderr)
            return 1
        except (HTTPException, OSError, ValueError) as error:
            print(f"Request {number}/{REQUEST_COUNT} failed: {error}", file=sys.stderr)
            return 1
        total_bytes += size
        total_seconds += elapsed

    average_seconds = total_seconds / REQUEST_COUNT
    speed_mbps = total_bytes * 8 / total_seconds / 1_000_000
    print(f"Requests: {REQUEST_COUNT}")
    print(f"Average request time: {average_seconds:.6f} s")
    print(f"Total downloaded: {total_bytes} bytes")
    print(f"Download speed: {speed_mbps:.3f} Mbit/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
