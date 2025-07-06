# Hacking on tinyweb

Run the typechecker

```bash
pip3 install mypy==1.16.1
mypy
```

Run the tests:

```
docker build . -t tinyweb # or podman
docker run --rm \
  -v ./test:/srv/tinyweb/test \
  -v ./tinyweb:/root/.micropython/lib/tinyweb \
  tinyweb micropython /srv/tinyweb/test/test_server.py
```

Run the linter

```bash
pip3 install ruff==0.12.1
ruff check && ruff format
```
