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

Install tinyweb on a board:

```bash
make build
mpremote mkdir :/lib \
    mkdir :/lib/tinyweb \
    cp ./dist/tinyweb/server.py :/lib/tinyweb/server.py
```

Run the example webapp:

```bash
mpremote mkdir :/srv/
mpremote cp ./examples/static/index.html :/srv/index.html
mpremote run ./examples/webapp.py
```
