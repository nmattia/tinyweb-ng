.PHONY: container build test clean

.DEFAULT_GOAL := build

DOCKER ?= docker
OUTDIR ?= ./dist
SERVER_PY := $(OUTDIR)/tinyweb/server.py
SERVER_MPY := $(OUTDIR)/tinyweb/server.mpy

build: $(SERVER_MPY) $(SERVER_PY)

$(SERVER_PY): ./tinyweb/server.py
	mkdir -p $(OUTDIR)/tinyweb
	strip-hints ./tinyweb/server.py -o $(OUTDIR)/tinyweb/server.py
	@sed -i.bak '/# TYPING_START/,/# TYPING_END/ s/.*//' $(SERVER_PY)
	@rm -f $(SERVER_PY).bak

$(SERVER_MPY): $(SERVER_PY)
	mpy-cross $(SERVER_PY)

container: Dockerfile
	$(DOCKER) build . -t tinyweb

test: build container
	# run with the local tinyweb mounted to the default search path
	# https://docs.micropython.org/en/latest/unix/quickref.html#envvar-MICROPYPATH
	$(DOCKER) run --rm \
		-v ./test:/opt/tinyweb-test \
		-v $(OUTDIR)/tinyweb:/root/.micropython/lib/tinyweb \
		tinyweb \
		micropython /opt/tinyweb-test/unit.py

lint: ./tinyweb/server.py
	ruff check
	mypy

clean:
	rm -rf $(OUTDIR)
