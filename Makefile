.PHONY: install test demo proof
install:
	python3 -m pip install -e .
test:
	python3 -m unittest discover -s tests -v
demo:
	python3 -m api_sync.cli
proof: test demo
	python3 -m api_sync.benchmark
