# Hacking on tinyweb

Run the linters

```bash
pip3 install -U micropython-rp2-rpi_pico2_w-stubs==1.25.0.post3 --target=./.typings
pip3 install mypy==1.16.1 ruff==0.12.1
make lint
```

Prepare output and run tests:

```
pip3 install strip-hints==0.1.13
make build
make test
```

## Install tinyweb on a board

First download MicroPython for your board [here](https://micropython.org/download/) and flash it to your board.

Then install the `logging` library:

```bash
mpremote mip install logging
```

Then build the lib:


```bash
make build
mpremote mkdir :/lib || true
mpremote mkdir :/lib/tinyweb || true
mpremote cp ./dist/tinyweb/server.py :/lib/tinyweb/server.py
```

Run the example webapp:

```bash
mpremote mkdir :/srv || true
mpremote cp ./examples/static/index.html :/srv/index.html
mpremote run ./examples/webapp.py
```
