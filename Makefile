PACKAGE=templdap
TESTS_DIR=tests

FLAKE8 = flake8

default:

clean:
	find . -type f -name '*.pyc' -delete
	find . -type f -path '*/__pycache__/*' -delete
	find . -type d -empty -delete

install-deps:
	pip install --upgrade pip setuptools
	pip install --upgrade -r requirements_dev.txt
	pip freeze

testall:
	tox

test:
	python -m unittest $(TESTS_DIR)

# Note: we run the linter in two runs, because our __init__.py files has specific warnings we want to exclude
lint:
	$(FLAKE8) --config .flake8 --exclude $(PACKAGE)/__init__.py $(PACKAGE) $(TESTS_DIR)
	$(FLAKE8) --config .flake8 --ignore F401 $(PACKAGE)/__init__.py
	check-manifest

