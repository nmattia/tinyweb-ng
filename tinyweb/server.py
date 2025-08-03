"""
Tiny Web - pretty simple and powerful web server for tiny platforms like ESP8266 / ESP32
MIT license
(C) Konstantin Belyalov 2017-2018
"""

import logging
import asyncio
import gc
import uos as os
import uerrno as errno

# TYPING_START
# typing related lines that get stripped during build
# (micropython doesn't support them)
from typing import Callable, TypedDict, Literal

# As per https://www.rfc-editor.org/rfc/rfc9112.html#name-request-line
RequestLine = TypedDict(
    "RequestLine",
    {
        "method": bytes,
        "target": bytes,
        "version": tuple[int, int],  # major.minor
    },
)

type Handler = Callable
Params = TypedDict(
    "Params",
    {
        "save_headers": list[bytes],
    },
)

# A route definition
# (method, path, handler, params)
type Route = tuple[bytes, bytes, Handler, Params]

type PathParameters = list[(bytes, bytes)]  # list of param name and param value
# TYPING_END

log = logging.getLogger("WEB")

# with v1.21.0 release all u-modules where renamend without the u prefix
# -> uasyncio no named asyncio
# asyncio v3 is shipped with MicroPython 1.13, and contains some subtle
# but breaking changes. See also https://github.com/peterhinch/micropython-async/blob/master/v3/README.md
IS_ASYNCIO_V3 = (
    hasattr(asyncio, "__version__")
    and asyncio.__version__ >= (3,)
    and asyncio.__version__ < (4,)
)

if not IS_ASYNCIO_V3:
    log.warning("tinyweb expects asyncio v3")


def urldecode_plus(s):
    """Decode urlencoded string (including '+' char).

    Returns decoded string
    """
    s = s.replace("+", " ")
    arr = s.split("%")
    res = arr[0]
    for it in arr[1:]:
        if len(it) >= 2:
            res += chr(int(it[:2], 16)) + it[2:]
        elif len(it) == 0:
            res += "%"
        else:
            res += it
    return res


def parse_query_string(s):
    """Parse urlencoded string into dict.

    Returns dict
    """
    res = {}
    pairs = s.split("&")
    for p in pairs:
        vals = [urldecode_plus(x) for x in p.split("=", 1)]
        if len(vals) == 1:
            res[vals[0]] = ""
        else:
            res[vals[0]] = vals[1]
    return res


def match_url_paths(route_path: bytes, req_path: bytes) -> None | PathParameters:
    """
    Match the 'route_path' to the 'req_path' and returns any path parameters.

    Returns None if there is no match.
    """
    path_params = []

    route_parts = route_path.split(b"/")
    req_parts = req_path.split(b"/")

    if len(route_parts) != len(req_parts):
        return None

    # go through the parts, accumulating any path parameters found
    # along the way.
    for route_part, req_part in zip(route_parts, req_parts):
        if route_part.startswith(b"<") and route_part.endswith(b">"):
            param_key = route_part[1:-1]
            param_val = req_part

            path_params.append((param_key, param_val))
            continue

        if route_part != req_part:
            return None

    return path_params


class HTTPException(Exception):
    """HTTP protocol exceptions"""

    def __init__(self, code=400):
        self.code = code


# per https://www.rfc-editor.org/rfc/rfc9110#table-4
SUPPORTED_METHODS = [
    b"GET",
    b"HEAD",
    b"POST",
    b"PUT",
    b"DELETE",
    b"CONNECT",
    b"OPTIONS",
    b"TRACE",
]


def parse_request_line(line: bytes) -> RequestLine | None:
    """
    As per https://www.rfc-editor.org/rfc/rfc9112.html#name-request-line
        request-line   = method SP request-target SP HTTP-version
    where SP is "single space"
    where method is defined in https://www.rfc-editor.org/rfc/rfc9110#section-9
    where request-target is arbitrary for our purposes
    where HTTP-version is 'HTTP-version  = HTTP-name "/" DIGIT "." DIGIT'
        (https://www.rfc-editor.org/rfc/rfc9112.html#name-http-version)
    """
    fragments = line.split(b" ")
    if len(fragments) != 3:
        return None

    if fragments[0] not in SUPPORTED_METHODS:
        return None

    if not fragments[1]:
        return None

    http_version_fragments = fragments[2].split(b"/")
    if len(http_version_fragments) != 2:
        return None

    if http_version_fragments[0] != b"HTTP":
        return None

    version_fragments = http_version_fragments[1].split(b".")

    if len(version_fragments) != 2:
        return None

    try:
        version_major = int(version_fragments[0])
        version_minor = int(version_fragments[1])
    except ValueError:  # failed to parse as int
        return None

    return {
        "method": fragments[0],
        "target": fragments[1],
        "version": (version_major, version_minor),
    }


class request:
    """HTTP Request class"""

    def __init__(self, _reader):
        self.reader: asyncio.StreamReader = _reader
        # headers are 'None' until `read_headers` is called
        self.headers: None | dict[bytes, bytes] = None
        self.method: bytes = b""
        self.path: bytes = b""
        self.query_string = b""
        self.version: Literal["1.0"] | Literal["1.1"] = "1.0"
        self.params: Params = {
            "save_headers": [],
        }

    async def read_request_line(self):
        """
        Read and parse first line (AKA HTTP Request Line).

        This updates the 'self' with the data. May raise a 400.
        """
        while True:
            rl_raw = await self.reader.readline()
            # skip empty lines
            if rl_raw == b"\r\n" or rl_raw == b"\n":
                continue
            break

        rl = parse_request_line(rl_raw)
        if not rl:
            raise HTTPException(400)

        self.method = rl["method"]

        url_frags = rl["target"].split(b"?", 1)

        self.path = url_frags[0]
        if len(url_frags) > 1:
            self.query_string = url_frags[1]

    async def read_headers(self, save_headers=[]):
        """Read and parse HTTP headers until \r\n\r\n:
        Optional argument 'save_headers' controls which headers to save.
            This is done mostly to deal with memory constrains.

        Function is generator.

        HTTP headers could be like:
        Host: google.com
        Content-Type: blah
        \r\n
        """
        self.headers = {}
        while True:
            gc.collect()
            line = await self.reader.readline()
            if line == b"\r\n":
                break
            frags = line.split(b":", 1)
            if len(frags) != 2:
                raise HTTPException(400)

            if frags[0].lower() in [header.lower() for header in save_headers]:
                self.headers[frags[0]] = frags[1].strip()


class response:
    """HTTP Response class"""

    VERSION = b"1.0"  # we only support 1.0

    def __init__(self, _writer):
        self._writer: asyncio.StreamWriter = _writer

        # Set to 'None' once the request line has been sent
        self._status_code: int | None = 200

        # Set to 'None' once the headers have been sent
        self.headers: dict[str, str] | None = {}

    async def _ensure_ready_for_body(self):
        status_line_sent = self._status_code is None
        headers_sent = self.headers is None

        if not status_line_sent:
            if headers_sent:
                raise Exception("Headers were sent before status line")
            await self._send_status_line()

        if not headers_sent:
            await self._send_headers()

    def set_status_code(self, value: int):
        if self._status_code is None:
            raise Exception("status line already sent")

        self._status_code = value

    async def send(self, content, **kwargs):
        await self._ensure_ready_for_body()

        self._writer.write(content)
        await self._writer.drain()

    async def _send_status_line(self):
        if self._status_code is None:
            raise Exception("status line already sent")

        _status_code = self._status_code
        self._status_code = None

        sl = "HTTP/{} {} MSG\r\n".format(response.VERSION.decode(), _status_code)
        self._writer.write(sl)
        await self._writer.drain()

    async def _send_headers(self):
        """
        Send headers followed by an empty line.
        """

        if self.headers is None:
            raise Exception("Headers already sent")

        _headers = self.headers
        self.headers = None

        hdrs = ""
        # Headers
        for k, v in _headers.items():
            hdrs += "{}: {}\r\n".format(k, v)
        hdrs += "\r\n"

        self._writer.write(hdrs)
        await self._writer.drain()
        # Collect garbage after small mallocs
        gc.collect()

    async def error(self, code, msg=None):
        """Generate HTTP error response
        This function is generator.

        Arguments:
            code - HTTP response code

        Example:
            # Not enough permissions. Send HTTP 403 - Forbidden
            await resp.error(403)
        """
        if self._status_code is None or self.headers is None:
            raise Exception("Status line already sent, cannot set status code")

        self._status_code = code
        if msg:
            self.add_header("Content-Length", len(msg))

        await self._send_status_line()
        await self._send_headers()

        if msg:
            await self.send(msg)

    async def redirect(self, location, msg=None):
        """Generate HTTP redirect response to 'location'.
        Basically it will generate HTTP 302 with 'Location' header

        Arguments:
            location - URL to redirect to

        Example:
            # Redirect to /something
            await resp.redirect('/something')
        """
        self._status_code = 302
        self.add_header("Location", location)
        if msg:
            self.add_header("Content-Length", len(msg))

        await self._send_status_line()
        await self._send_headers()

        if msg:
            await self.send(msg)

    def add_header(self, key, value):
        """Add HTTP response header

        Arguments:
            key - header name
            value - header value

        Example:
            resp.add_header('Content-Encoding', 'gzip')
        """
        if self.headers is None:
            raise Exception("Headers already sent")

        self.headers[key] = value

    async def start_html(self):
        """Start response with HTML content type.
        This function is generator.

        Example:
            await resp.start_html()
            await resp.send('<html><h1>Hello, world!</h1></html>')
        """
        self.add_header("Content-Type", "text/html")

    async def send_file(
        self,
        filename,
        content_type=None,
        content_encoding=None,
        max_age=2592000,
        buf_size=128,
    ):
        """Send local file as HTTP response.
        This function is generator.

        Arguments:
            filename - Name of file which exists in local filesystem
        Keyword arguments:
            content_type - Filetype. By default - None means auto-detect.
            max_age - Cache control. How long browser can keep this file on disk.
                      By default - 30 days
                      Set to 0 - to disable caching.

        Example 1: Default use case:
            await resp.send_file('images/cat.jpg')

        Example 2: Disable caching:
            await resp.send_file('static/index.html', max_age=0)

        Example 3: Override content type:
            await resp.send_file('static/file.bin', content_type='application/octet-stream')
        """
        try:
            # Get file size
            stat = os.stat(filename)
            file_len = stat[6]
            self.add_header("Content-Length", str(file_len))
            # Find content type
            if content_type:
                self.add_header("Content-Type", content_type)
            # Add content-encoding, if any
            if content_encoding:
                self.add_header("Content-Encoding", content_encoding)
            # Since this is static content is totally make sense
            # to tell browser to cache it, however, you can always
            # override it by setting max_age to zero
            self.add_header("Cache-Control", "max-age={}, public".format(max_age))
            with open(filename) as f:
                await self._send_status_line()
                await self._send_headers()
                gc.collect()
                buf = bytearray(min(file_len, buf_size))
                while True:
                    size = f.readinto(buf)
                    if size == 0:
                        break
                    await self.send(buf[:size])
        except OSError as e:
            # special handling for ENOENT / EACCESS
            if e.args[0] in (errno.ENOENT, errno.EACCES):
                raise HTTPException(404)
            else:
                raise


class webserver:
    def __init__(self, request_timeout=3, backlog=16, debug=False):
        """Tiny Web Server class.
        Keyword arguments:
            request_timeout - Time for client to send complete request
                              after that connection will be closed.
            backlog         - Parameter to asyncio.start_server() function.
                              Defines size of pending to be accepted connections
                              queue.
            debug           - Whether send exception info (text + backtrace)
                              to client together with HTTP 500 or not.
        """
        self.server: asyncio.Server | None = None
        self.loop = asyncio.get_event_loop()
        self.request_timeout = request_timeout
        self.backlog = backlog
        self.debug = debug
        self.routes: list[Route] = []
        self.catch_all_handler = None

    def _find_url_handler(self, req) -> tuple[Handler, Params, PathParameters]:
        """Helper to find URL handler.
        Returns tuple of (function, params) or HTTPException (404 or 405) if not found.

        raises: HTTPException
        """

        # we only support basic (GET, PUT, etc) requests
        if (
            req.method == b"CONNECT"
            or req.method == b"OPTIONS"
            or req.method == b"TRACE"
        ):
            raise HTTPException(501)

        # tracks whether there was an exact path match to differentiate
        # between 404 and 405
        path_matched = False

        for method, path, handler, params in self.routes:
            result = match_url_paths(path, req.path)
            if result is not None:
                if method == req.method:
                    return (handler, params, result)

                path_matched = True

        if self.catch_all_handler:
            return self.catch_all_handler

        if path_matched:
            raise HTTPException(405)

        # No handler found
        raise HTTPException(404)

    async def _handle_connection(self, reader, writer):
        """Handler for TCP connection with
        HTTP/1.0 protocol implementation
        """
        gc.collect()

        try:
            req = request(reader)
            resp = response(writer)
            await req.read_request_line()

            # Find URL handler and parse headers
            (handler, req_params, path_params) = self._find_url_handler(req)
            await req.read_headers(req_params.get("save_headers") or [])

            gc.collect()  # free up some memory before the handler runs

            path_param_values = [v.decode() for (_, v) in path_params]
            await handler(req, resp, *path_param_values)

            # ensure the status line & headers are sent even if there
            # was no body
            await resp._ensure_ready_for_body()
            # Done here
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except OSError as e:
            # Do not send response for connection related errors - too late :)
            # P.S. code 32 - is possible BROKEN PIPE error (TODO: is it true?)
            if e.args[0] not in (errno.ECONNABORTED, errno.ECONNRESET, 32):
                try:
                    await resp.error(500)
                except Exception as e:
                    log.exception(
                        f"Failed to send 500 error after OSError. Original error: {e}"
                    )
        except HTTPException as e:
            try:
                if req.headers is None:
                    await req.read_headers()
                await resp.error(e.code)
            except Exception as e:
                log.exception(
                    f"Failed to send error after HTTPException. Original error: {e}"
                )
        except Exception as e:
            # Unhandled expection in user's method
            log.error(req.path.decode())
            log.exception(f"Unhandled exception in user's method. Original error: {e}")
            try:
                await resp.error(500)
            except Exception as e:
                pass
        finally:
            writer.close()
            await writer.wait_closed()

    def add_route(
        self,
        url: str,
        f,
        methods: list[str] = ["GET"],
        save_headers: list[str | bytes] = [],
    ):
        """Add URL to function mapping.

        Arguments:
            url - url to map function with
            f - function to map

        Keyword arguments:
            methods - list of allowed methods. Defaults to ['GET', 'POST']
            save_headers - contains list of HTTP headers to be saved. Case sensitive. Default - empty.
        """
        if url == "" or "?" in url:
            raise ValueError("Invalid URL")
        _save_headers = [x.encode() if isinstance(x, str) else x for x in save_headers]
        _save_headers = [x.lower() for x in _save_headers]
        # Initial params for route
        params: Params = {
            "save_headers": _save_headers,
        }

        for method in [x.encode().upper() for x in methods]:
            self.routes.append((method, url.encode(), f, params))

    def catchall(self):
        """Decorator for catchall()

        Example:
            @app.catchall()
            def catchall_handler(req, resp):
                response._status_code = 404
                await response.start_html()
                await response.send('<html><body><h1>My custom 404!</h1></html>\n')
        """
        params: Params = {
            "save_headers": [],
        }

        def _route(f):
            self.catch_all_handler = (f, params, {})
            return f

        return _route

    def route(self, url, **kwargs):
        """Decorator for add_route()

        Example:
            @app.route('/')
            def index(req, resp):
                await resp.start_html()
                await resp.send('<html><body><h1>Hello, world!</h1></html>\n')
        """

        def _route(f):
            self.add_route(url, f, **kwargs)
            return f

        return _route

    def run(self, host="127.0.0.1", port=8081, loop_forever=True):
        """Run Web Server. By default it runs forever.

        Keyword arguments:
            host - host to listen on. By default - localhost (127.0.0.1)
            port - port to listen on. By default - 8081
            loop_forever - run loo.loop_forever(), otherwise caller must run it by itself.
        """
        self.server = asyncio.run(
            asyncio.start_server(
                self._handle_connection, host, port, backlog=self.backlog
            )
        )
        if loop_forever:
            self.loop.run_forever()

    def shutdown(self):
        """Gracefully shutdown Web Server"""
        if self.server:
            self.server.close()
