# uht

A minimal HTTP/1.0 server for tiny devices (ESP32, Raspberry Pi Pico, etc.) running [MicroPython](https://github.com/micropython/micropython) or [CircuitPython](https://github.com/adafruit/circuitpython). Compatible with MicroPython 1.21+.

## Getting Started

### Installation

Please refer to the [HACKING](./HACKING.md) document.

## Basic Usage

```python
from uht import HTTPServer

app = HTTPServer()

@app.route("/")
async def index(req, resp):
    await resp.send(b"Hello, world!")

app.run()  # Starts the server on 127.0.0.1:8081
```

## Supported Features

* HTTP/1.0 support
* Route handling with method-based dispatch
* Path parameters (`/user/<id>`)
* Custom response headers
* Custom status codes and phrases
* Catch-all handler

### Limitations

* Only supports HTTP/1.0
* No SSL/TLS
* No built-in static file serving

## Examples

### Basic Hello World

Serve a simple "Hello, world!" response on `http://127.0.0.1:8081/`:

```python
from uht import HTTPServer

app = HTTPServer()

@app.route("/")
async def index(req, resp):
    await resp.send(b"Hello, world!")

app.run()  # Defaults to 127.0.0.1:8081
```

### Route with Parameter

Define a dynamic route that greets the user by name:

```python
@app.route("/hello/<name>")
async def greet(req, resp, name):
    await resp.send(f"Hello, {name}!".encode())
```

The parameter is now echoed in the response:

```bash
$ curl http://127.0.0.1:8081/hello/Alice
Hello, Alice!
```

### Custom Status Code and Header

Custom HTTP status codes and additional response headers can be set as follows:

```python
@app.route("/custom")
async def custom_response(req, resp):
    resp.set_status_code(202)
    resp.set_reason_phrase("Accepted")
    resp.add_header("X-Custom", "Value")
    await resp.send(b"Custom response")
```

> [!NOTE]
>
> The status code and headers must be set before the first call to `send()` otherwise an exception will be thrown!

Response:

```
HTTP/1.0 202 Accepted
X-Custom: Value
```

### Catch-All Route

A catch-all handler can be registered:

```python
@app.catchall()
async def not_found(req, resp):
    resp.set_status_code(404)
    await resp.send(b"Custom 404 Not Found")
```

Any request that doesn't match a defined route will now return:
```
HTTP/1.0 404
Custom 404 Not Found
```

See the [examples](./examples) directory for more.

## Running in an Async Context

If you need to integrate the server with other async code (e.g., background tasks), use the `start()` method instead of `run()`.

### Example:

```python
from uht import HTTPServer
import asyncio

app = HTTPServer()

@app.route("/")
async def index(req, resp):
    await resp.send(b"Hello from async start")

async def main():
    server = app.start("0.0.0.0", 8081)
    print("Server started on port 8081")

    # Optionally do other async tasks here
    await server.wait_closed()  # Wait until the server shuts down

asyncio.run(main())
```

This approach gives you more control and allows you to schedule other coroutines alongside the HTTP server.
