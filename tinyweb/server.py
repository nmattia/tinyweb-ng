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
from typing import Callable, TypedDict

type Handler = Callable
Params = TypedDict(
    "Params",
    {
        "max_body_size": int,
        "methods": list[bytes],
        "save_headers": list[bytes],
        "allowed_access_control_headers": str,
        "allowed_access_control_origins": str,
        "allowed_access_control_methods": str,
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


class request:
    """HTTP Request class"""

    def __init__(self, _reader):
        self.handler: None | Callable = None
        self.reader: asyncio.StreamReader = _reader
        self.headers = {}
        self.method: bytes = b""
        self.path: bytes = b""
        # parsed named path parameters (if the route defines any)
        self.path_params: PathParameters = []
        self.query_string = b""
        self.params: Params = {
            "methods": [b"GET"],
            "save_headers": [],
            "max_body_size": 1024,
            "allowed_access_control_headers": "*",
            "allowed_access_control_origins": "*",
            "allowed_access_control_methods": "GET",
        }

    async def read_request_line(self):
        """Read and parse first line (AKA HTTP Request Line).
        Function is generator.

        Request line is something like:
        GET /something/script?param1=val1 HTTP/1.1
        """
        while True:
            rl = await self.reader.readline()
            # skip empty lines
            if rl == b"\r\n" or rl == b"\n":
                continue
            break
        rl_frags = rl.split()
        if len(rl_frags) != 3:
            raise HTTPException(400)
        self.method = rl_frags[0]
        url_frags = rl_frags[1].split(b"?", 1)
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

    def __init__(self, _writer):
        self._writer: asyncio.StreamWriter = _writer
        self.code = 200
        self.version = "1.0"
        self.headers = {}
        self.params: dict = {}

    async def send(self, content, **kwargs):
        self._writer.write(content)
        await self._writer.drain()

    async def _send_headers(self):
        """Compose and send:
        - HTTP request line
        - HTTP headers following by \r\n.
        This function is generator.

        P.S.
        Because of usually we have only a few HTTP headers (2-5) it doesn't make sense
        to send them separately - sometimes it could increase latency.
        So combining headers together and send them as single "packet".
        """
        # Request line
        hdrs = "HTTP/{} {} MSG\r\n".format(self.version, self.code)
        # Headers
        for k, v in self.headers.items():
            hdrs += "{}: {}\r\n".format(k, v)
        hdrs += "\r\n"
        # Collect garbage after small mallocs
        gc.collect()
        await self.send(hdrs)

    async def error(self, code, msg=None):
        """Generate HTTP error response
        This function is generator.

        Arguments:
            code - HTTP response code

        Example:
            # Not enough permissions. Send HTTP 403 - Forbidden
            await resp.error(403)
        """
        self.code = code
        if msg:
            self.add_header("Content-Length", len(msg))
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
        self.code = 302
        self.add_header("Location", location)
        if msg:
            self.add_header("Content-Length", len(msg))
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
        self.headers[key] = value

    def add_access_control_headers(self):
        """Add Access Control related HTTP response headers.
        This is required when working with RestApi (JSON requests)
        """
        self.add_header(
            "Access-Control-Allow-Origin", self.params["allowed_access_control_origins"]
        )
        self.add_header(
            "Access-Control-Allow-Methods",
            self.params["allowed_access_control_methods"],
        )
        self.add_header(
            "Access-Control-Allow-Headers",
            self.params["allowed_access_control_headers"],
        )

    async def start_html(self):
        """Start response with HTML content type.
        This function is generator.

        Example:
            await resp.start_html()
            await resp.send('<html><h1>Hello, world!</h1></html>')
        """
        self.add_header("Content-Type", "text/html")
        await self._send_headers()

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

    def _find_url_handler(
        self, req
    ) -> tuple[Handler, Params, PathParameters] | HTTPException:
        """Helper to find URL handler.
        Returns tuple of (function, params) or HTTPException (404 or 405) if not found.
        """

        async def handle_options(req, resp):
            resp.add_access_control_headers()
            # Since we support only HTTP 1.0 - it is important
            # to tell browser that there is no payload expected
            # otherwise some webkit based browsers (Chrome)
            # treat this behavior as an error
            resp.add_header("Content-Length", "0")
            await resp._send_headers()
            return

        if req.method == b"OPTIONS":
            params: Params = {
                "methods": [b"GET"],
                "save_headers": [],
                "max_body_size": 1024,
                "allowed_access_control_headers": "*",
                "allowed_access_control_origins": "*",
                "allowed_access_control_methods": "POST, PUT, DELETE",
            }

            return (handle_options, params, [])

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
            return HTTPException(405)

        # No handler found
        return HTTPException(404)

    async def _handle_request(self, req, resp):
        await req.read_request_line()
        # Find URL handler
        result = self._find_url_handler(req)

        if isinstance(result, HTTPException):
            # No URL handler found - read response and issue HTTP 404
            await req.read_headers()
            raise result

        (handler, req_params, path_params) = result

        req.handler = handler
        req.params = req_params
        req.path_params = path_params
        resp.params = req.params
        # Read / parse headers
        await req.read_headers(req.params.get("save_headers") or [])

    async def _handler(self, reader, writer):
        """Handler for TCP connection with
        HTTP/1.0 protocol implementation
        """
        gc.collect()

        try:
            req = request(reader)
            resp = response(writer)
            # Read HTTP Request with timeout
            await asyncio.wait_for(
                self._handle_request(req, resp), self.request_timeout
            )

            if not req.handler:
                raise HTTPException(500)

            # Handle URL
            gc.collect()

            path_param_values = [v.decode() for (_, v) in req.path_params]
            await req.handler(req, resp, *path_param_values)
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
        save_headers: list[str] = [],
        **kwargs,
    ):
        """Add URL to function mapping.

        Arguments:
            url - url to map function with
            f - function to map

        Keyword arguments:
            methods - list of allowed methods. Defaults to ['GET', 'POST']
            save_headers - contains list of HTTP headers to be saved. Case sensitive. Default - empty.
            max_body_size - Max HTTP body size (e.g. POST form data). Defaults to 1024
            allowed_access_control_headers - Default value for the same name header. Defaults to *
            allowed_access_control_origins - Default value for the same name header. Defaults to *
        """
        if url == "" or "?" in url:
            raise ValueError("Invalid URL")
        # Initial params for route
        params = {
            "methods": methods,
            "save_headers": save_headers,
            "max_body_size": 1024,
            "allowed_access_control_headers": "*",
            "allowed_access_control_origins": "*",
        }
        params["allowed_access_control_methods"] = ", ".join(methods)
        # Convert methods/headers to bytestring
        methods_bytes: list[bytes] = [x.encode().upper() for x in methods]
        params["methods"] = methods_bytes
        params.update(kwargs)
        params["save_headers"] = [x.encode().lower() for x in save_headers]

        _params: Params = params  # type: ignore
        for method in methods_bytes:
            self.routes.append((method, url.encode(), f, _params))

    def catchall(self):
        """Decorator for catchall()

        Example:
            @app.catchall()
            def catchall_handler(req, resp):
                response.code = 404
                await response.start_html()
                await response.send('<html><body><h1>My custom 404!</h1></html>\n')
        """
        params = {
            "methods": [b"GET"],
            "save_headers": [],
            "max_body_size": 1024,
            "allowed_access_control_headers": "*",
            "allowed_access_control_origins": "*",
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
            asyncio.start_server(self._handler, host, port, backlog=self.backlog)
        )
        if loop_forever:
            self.loop.run_forever()

    def shutdown(self):
        """Gracefully shutdown Web Server"""
        if self.server:
            self.server.close()
