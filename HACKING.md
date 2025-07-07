# Hacking on tinyweb

Run the linters

```bash
pip3 install mypy==1.16.1 ruff==0.12.1
make lint
```

Prepare output and run tests:

```
pip3 install strip-hints==0.1.13
make build
make test
```
