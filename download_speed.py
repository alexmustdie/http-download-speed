"""Measure HTTP download speed with ten sequential GET requests."""

import argparse
import math
import sys
from http.client import HTTPException
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024
DEFAULT_TIMEOUT = 30


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
        raise argparse.ArgumentTypeError("expected a positive number of seconds") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite number of seconds")
    return seconds


def download(opener, url, timeout):
    request = Request(url, headers={"Accept-Encoding": "identity"})
    start = perf_counter()
    with opener.open(request, timeout=timeout) as response:
        size = 0
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)

        # A bounded read can return EOF without raising on a short body.
        length = response.headers.get("Content-Length")
        if length is not None and not response.headers.get("Transfer-Encoding"):
            if size != int(length):
                raise HTTPException(f"incomplete response: got {size} of {length} bytes")
    return size, perf_counter() - start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", type=http_url, help="direct URL of a downloadable file")
    parser.add_argument(
        "--timeout",
        type=positive_seconds,
        default=DEFAULT_TIMEOUT,
        help="socket timeout in seconds (default: %(default)s)",
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
