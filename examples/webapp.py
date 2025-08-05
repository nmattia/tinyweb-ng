#!/usr/bin/env micropython

import gc
import json
import sys
import tinyweb
import logging
import network


def init_logger(name="root"):
    rootLogger = logging.getLogger(name)
    rootLogger.setLevel(logging.DEBUG)
    for handler in rootLogger.handlers:
        handler.setLevel(logging.DEBUG)


init_logger("root")
init_logger("WEB")

server = tinyweb.HTTPServer()


@server.route("/", methods=["GET"])
async def get_index(req, resp):
    """Serve the webapp."""
    await resp.send_file("/srv/index.html")


@server.route("/info", methods=["GET"])
async def get_info(req, resp):
    """Returns information about the board."""
    resp.headers[b"content-type"] = b"application/json"

    obj = board_data()

    await resp._send_headers()
    await resp.send(json.dumps(obj))


@server.route("/pins/", methods=["GET"])
async def get_pins(req, resp):
    """Returns a list of pins."""
    from machine import Pin

    pin_names: list[str] = []

    for pin in dir(Pin.board):
        if not pin.startswith("__"):
            pin_names.append(pin)

    resp.headers[b"content-type"] = b"application/json"
    await resp._send_headers()
    await resp.send(json.dumps({"pins": pin_names}))


@server.route("/pins/<pin_name>/toggle", methods=["POST"])
async def toggle_pin(req, resp, pin_name):
    """Toggles any particular pin."""

    from machine import Pin

    pin = getattr(Pin.board, pin_name)
    pin.toggle()

    resp.headers[b"content-type"] = b"application/json"
    await resp._send_headers()
    await resp.send(json.dumps({}))


def board_data():
    """Return boad data in format [{"title": "foo", "value": "bar"}]."""

    obj = [{"title": "Platform", "value": sys.platform}]

    # some of these are not available on all platforms, so as much as possible we wrap them in try/catch
    try:
        ap = network.WLAN(network.AP_IF)
        if ap.active():
            (ip, _, _, _) = ap.ifconfig()
            obj.append({"title": "Network", "value": f"{ip} (AP mode)"})
    except ModuleNotFoundError:
        pass

    try:
        mem_free = gc.mem_free()
        mem_tot = mem_free + gc.mem_alloc()
        mem_data = f"{mem_free}B/{mem_tot}B ({mem_free / mem_tot * 100:.2}%)"
        obj.append({"title": "Memory Usage", "value": mem_data})
    except ModuleNotFoundError:
        pass

    try:
        import machine

        # while the freq (as a string) ends with 000, increase the 10e3 factor
        # in the unit and strip those three 0s
        freq = str(machine.freq())
        freq_unit_factor = ["", "k", "M", "G", "T"]  # Hz, kHz, MHz, etc
        freq_10e3 = 0
        while freq.endswith("000"):
            freq = freq[:3]
            freq_10e3 += 1

        freq = f"{freq}{freq_unit_factor[freq_10e3]}Hz"
        obj.append({"title": "Chip Frequency", "value": freq})
    except ModuleNotFoundError:
        pass

    return obj


def run():
    # Set up AP
    SSID = "tinyweb"
    logging.info(f"creating AP with SSID '{SSID}'")
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(ssid="tinyweb", security=network.WLAN.SEC_OPEN)

    (ip, _, _, _) = ap.ifconfig()
    logging.info("AP configured: " + ip)

    port = 8081
    logging.info("starting server")
    endpoint = f"http://{ip}:{port}"
    logging.info(f"listening on '{endpoint}'")
    server.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
