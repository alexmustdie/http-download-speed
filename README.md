# HTTP Download Speed

A Python CLI that measures download speed from a single HTTP or HTTPS URL.
Requires Python 3.9 or later and uses only the standard library.

```sh
python3 download_speed.py 'https://your-server.example/large-file'
```

Replace the example URL with a direct link to a file. Redirects are reported
as errors; use the final URL. The script stops on the first failed request,
reports the error on stderr, and exits with status 1.

The script performs 10 sequential GETs and reads each response body in chunks.
Request time runs from opening the connection through reading the entire body.
The reported average is the sum of the 10 request times divided by 10. The
total counts body bytes only, without HTTP headers or transfer framing.
Speed is (total bytes × 8) / (sum of request times × 1,000,000), in decimal
megabits per second (Mbit/s). It reflects the path to the chosen server and
includes connection setup and server response time.

Use `--timeout SECONDS` to change the socket timeout (default: 30 seconds).
This limits individual blocking socket operations.

Run the local HTTP integration tests with:

```sh
python3 -m unittest discover -s tests -v
```
