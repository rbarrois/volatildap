PACKAGE=volatildap
TESTS_DIR=tests

FLAKE8 = flake8

default:

clean:
	find . -type f -name '*.pyc' -delete
	find . -type f -path '*/__pycache__/*' -delete
	find . -type d -empty -delete

upgrade:
	pip install --upgrade pip setuptools
	pip install --upgrade -r requirements_dev.txt
	pip freeze

release:
	fullrelease

.PHONY: default clean upgrade release

testall:
	tox

test:
	python -Wdefault -m unittest discover $(TESTS_DIR)

.PHONY: test testall

# Note: we run the linter in two runs, because our __init__.py files has specific warnings we want to exclude
lint: flake8 isort check-manifest

flake8:
	$(FLAKE8) --config .flake8 --exclude $(PACKAGE)/__init__.py $(PACKAGE) $(TESTS_DIR)
	$(FLAKE8) --config .flake8 --ignore F401 $(PACKAGE)/__init__.py

isort:
	isort $(PACKAGE) $(TESTS_DIR) --recursive --check-only --diff --project $(PACKAGE) --project $(TESTS_DIR)

check-manifest:
	check-manifest

.PHONY: lint flake8 isort check-manifest
