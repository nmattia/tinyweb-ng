# Hacking on tinyweb


Run the tests:

```
docker build . -t tinyweb # or podman
docker run --rm \
  -v ./test:/srv/tinyweb/test \
  -v ./tinyweb:/root/.micropython/lib/tinyweb \
  tinyweb micropython /srv/tinyweb/test/test_server.py
```
