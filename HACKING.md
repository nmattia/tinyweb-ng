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

First MicroPython (or CircuitPython) needs to be installed on your board. Then the dependencies need to be installed. Then you can install tinyweb.

### Installing MicroPython

First download MicroPython for your board [here](https://micropython.org/download/) and flash it to your board.

<details><summary><h4>Install MicroPython on Raspberry Pi Pico 2 W</h4></summary>

1. Download the [MicroPython `.uf2` release](https://micropython.org/download/RPI_PICO2_W/)
2. Enter bootloader mode by holding the BOOTSEL button while powering your device
3. Copy the MicroPython `.uf2` to your device

</details>

<details><summary><h4>Install MicroPython on ESP8266</h4></summary>

```bash
pip3 install esptool==5.0.1
esptool erase_flash
curl -LO https://micropython.org/resources/firmware/ESP8266_GENERIC-20250415-v1.25.0.bin
esptool write-flash --flash-size=detect 0 ./ESP8266_GENERIC-20250415-v1.25.0.bin
```

</details>

<details><summary><h4>Install MicroPython on ESP32-C6</h4></summary>

```bash
pip3 install esptool==5.0.1
esptool erase_flash
curl -LO https://micropython.org/resources/firmware/ESP32_GENERIC_C6-20250415-v1.25.0.bin
esptool write-flash --flash-size=detect 0 ./ESP32_GENERIC_C6-20250415-v1.25.0.bin
```

</details>


### Installing dependencies

Install the `logging` library with the following command:

```bash
mpremote mip install logging
```

```bash
pip3 install mpy-cross==1.25.0.post2
mpy-cross ./dist/tinyweb/server.py
mpremote cp ./dist/tinyweb/server.mpy :/lib/tinyweb/server.mpy
```

### Install tinyweb

Build the tinyweb server library with the following commands:

```bash
mpremote mkdir :/lib || true
mpremote mkdir :/lib/tinyweb || true
make ./dist/tinyweb/server.py
mpremote cp ./tinyweb/__init__.py :/lib/tinyweb/__init__.py
mpremote cp ./dist/tinyweb/server.py :/lib/tinyweb/server.py
```

Run the example webapp:

```bash
mpremote mkdir :/srv || true
mpremote cp ./examples/static/index.html :/srv/index.html
mpremote run ./examples/webapp.py
```

Run the tests on a board:

```
mpremote mip install unittest
mpremote run ./test/unit.py
```
