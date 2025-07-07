.PHONY: container build test

DOCKER ?= docker
OUTDIR ?= ./dist


OUTFILE = $(OUTDIR)/tinyweb/server.py

build: $(OUTFILE)

$(OUTFILE): ./tinyweb/server.py
	mkdir -p $(OUTDIR)/tinyweb
	strip-hints ./tinyweb/server.py -o $(OUTFILE)
	@sed -i.bak '/# TYPING_START/,/# TYPING_END/d' $(OUTFILE)
	@rm -f $(OUTFILE).bak

container: Dockerfile
	$(DOCKER) build . -t tinyweb

test: build container
	# run with the local tinyweb mounted to the default search path
	# https://docs.micropython.org/en/latest/unix/quickref.html#envvar-MICROPYPATH
	$(DOCKER) run --rm \
		-v ./test:/srv/tinyweb/test \
		-v $(OUTDIR)/tinyweb:/root/.micropython/lib/tinyweb \
		tinyweb \
		micropython /srv/tinyweb/test/test_server.py

lint: ./tinyweb/server.py
	ruff check
	mypy
