# tinyweb

A simple and lightweight (thus *tiny*) HTTP server for tiny devices (ESP32, Raspberry Pi Pico, etc.) running [MicroPython](https://github.com/micropython/micropython).

Having a simple HTTP server allows developers to create modern UIs for their IoT devices.
By itself, *tinyweb* is just a simple HTTP server running on top of [`uasyncio`](https://github.com/micropython/micropython-lib/tree/v1.0/uasyncio)—a library for MicroPython. Therefore, *tinyweb* is a single-threaded server.

> [!NOTE]
> This library was forked and adapted from [belyalov/tinyweb](https://github.com/belyalov/tinyweb)

### Features

* Fully asynchronous when used with the [uasyncio](https://github.com/micropython/micropython-lib/tree/v1.0/uasyncio) library for MicroPython.
* [Flask](http://flask.pocoo.org/) / [Flask-RESTful](https://flask-restful.readthedocs.io/en/latest/)-like API.
* *Tiny* memory usage—so you can run it on devices like **ESP8266 / ESP32** with only 64K/96K of onboard RAM.
* Support for serving static content from the filesystem.

### Requirements

* MicroPython 1.25 or newer
* [`logging`](https://github.com/micropython/micropython-lib/tree/master/python-stdlib/logging)

---

#### Hello World

Let's write a [Hello World](https://github.com/nmattia/tinyweb-ng/blob/master/examples/hello_world.py) app from scratch:

```python
import tinyweb

# Create the web server application
app = tinyweb.webserver()

# Index page
@app.route('/')
async def index(request, response):
    await response.start_html()  # Start HTTP response with content-type text/html
    await response.send('<html><body><h1>Hello, world! (<a href="/table">table</a>)</h1></html>
')

# A more complicated page
@app.route('/table')
async def table(request, response):
    await response.start_html()
    await response.send('<html><body><h1>Simple table</h1>'
                        '<table border=1 width=400>'
                        '<tr><td>Name</td><td>Some Value</td></tr>')
    for i in range(10):
        await response.send('<tr><td>Name{}</td><td>Value{}</td></tr>'.format(i, i))
    await response.send('</table></html>')

def run():
    app.run(host='0.0.0.0', port=8081)
```

Simple? Let’s try it!
Flash your device with the firmware, open the REPL, and type:

```python
>>> import network

# Connect to WiFi
>>> sta_if = network.WLAN(network.STA_IF)
>>> sta_if.active(True)
>>> sta_if.connect('<ssid>', '<password>')

# Run Hello World! :)
>>> import examples.hello_world as hello
>>> hello.run()
```

That’s it! :)
Try it by opening: `http://<your ip>:8081`

Like it? Check out more [examples](./examples)!

---

### Limitations

* HTTP protocol support: Due to memory constraints, only **HTTP/1.0** is supported (with the exception of REST API, which uses HTTP/1.1 with `Connection: close`). Support for HTTP/1.1 may be added when the `esp8266` platform is fully deprecated.

---

### Reference

#### class `webserver`

Main *tinyweb* app class.

* `__init__(self, request_timeout=3, max_concurrency=None, backlog=10, debug=False)`
    * `request_timeout` – Timeout for the client to send a complete HTTP request (excluding body). After that, the connection will be closed. Since `uasyncio` has a small event queue (~42 items), avoid values > 5 to prevent overflow.
    * `max_concurrency` – Maximum number of concurrent connections. This is important due to memory constraints. Default values: **3** (ESP8266), **6** (ESP32), **10** (others).
    * `backlog` – Passed to `socket.listen()`. Defines the size of the queue for pending connections. Must be ≥ `max_concurrency`.
    * `debug` – If `True`, exception text + backtrace will be sent to the client along with HTTP 500.

* `add_route(self, url, f, **kwargs)` – Map a `url` to function `f`.
  Keyword arguments:
    * `methods` – Allowed HTTP methods (default: `['GET', 'POST']`).
    * `save_headers` – List of headers to save. To reduce memory usage, specify only what you need (e.g., `'Content-Length'` for POST requests). Default: `[]`.
    * `max_body_size` – Max HTTP body size (default: `1024`). Be cautious on low-RAM devices like ESP8266.
    * `allowed_access_control_headers` – Required for CORS (e.g., if sending JSON via XMLHttpRequest). Default: `*`.
    * `allowed_access_control_origins` – Same as above. Default: `*`.

* `@route` – A convenient decorator (inspired by *Flask*). Instead of `add_route()`, use:
    ```python
    @app.route('/index.html')
    async def index(req, resp):
        await resp.send_file('static/index.simple.html')
    ```

* `run(self, host="127.0.0.1", port=8081, loop_forever=True, backlog=10)` – Run the web server.
  * `loop_forever` – If `True`, runs `asyncio.loop_forever()`. Set to `False` if you want to manage the loop yourself.

* `shutdown(self)` – Gracefully shut down the server. Closes sockets and cancels tasks.
  **Note**: Make sure it runs in the event loop:
    ```python
    async def all_shutdown():
        await asyncio.sleep_ms(100)

    try:
        web = tinyweb.webserver()
        web.run()
    except KeyboardInterrupt:
        print('CTRL+C pressed - terminating...')
        web.shutdown()
        uasyncio.get_event_loop().run_until_complete(all_shutdown())
    ```

---

#### class `request`

Encapsulates the HTTP request.

> ⚠️ Note: All strings in `request` are *binary strings* for performance. Always use `b''` notation.

* `method` – HTTP method (e.g., `b'GET'`)
* `path` – URL path
* `query_string` – Query string from the URL
* `headers` – Dictionary of saved headers (if `save_headers` was used)
    ```python
    if b'Content-Length' in self.headers:
        print(self.headers[b'Content-Length'])
    ```

* `read_parse_form_data()` – Manually parse form data. Returns a dictionary of key/value pairs.
  (REST APIs parse automatically.)

---

#### class `response`

Generates HTTP responses.
Unlike `request`, `response` uses *regular strings*.

* `code` – HTTP status code (default: `200`)
* `version` – HTTP version (`1.0` by default; `1.1` is unsupported internally)
* `headers` – Dictionary of headers

Methods:

* `add_header(key, value)` – Add a response header
* `add_access_control_headers()` – Adds CORS headers
* `redirect(location)` – Coroutine that sends a 302 redirect
* `start_html()` – Coroutine that starts a response with `Content-Type: text/html`
* `send(payload)` – Coroutine to send `payload` (string/bytes)
* `send_file(filename, **kwargs)` – Sends a file from the filesystem
  Optional args:
    * `content_type` – MIME type (default: autodetect)
    * `content_encoding` – e.g., `'gzip'`
    * `max_age` – Cache lifetime in seconds (default: 30 days; set `0` to disable)
* `error(code)` – Coroutine that sends an HTTP error with status `code`
