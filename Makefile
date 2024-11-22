# Variables
PYTHON = python3
VENV_DIR = .venv
ACTIVATE = source $(VENV_DIR)/bin/activate
SRC_DIR = src
TEST_DIR = tests
REQ_FILE = requirements.txt

.PHONY: all install test lint clean run

# Default target
all: install lint test run

# Create a virtual environment and install dependencies
$(VENV_DIR):
	$(PYTHON) -m venv $(VENV_DIR)
	$(ACTIVATE) && pip install --upgrade pip

install: $(VENV_DIR)
	$(ACTIVATE) && pip install -r $(REQ_FILE)

# Run tests using pytest
test:
	$(ACTIVATE) && pytest $(TEST_DIR)

# Lint the code using flake8
lint:
	$(ACTIVATE) && flake8 $(SRC_DIR) $(TEST_DIR)

# Run the application
run:
	$(ACTIVATE) && $(PYTHON) -m $(SRC_DIR).main

# Clean up temporary files
clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	rm -rf $(VENV_DIR)
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .coverage
	rm -rf htmlcov

# Additional help target
help:
	@echo "Usage:"
	@echo "  make install   - Create virtual environment and install dependencies"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Lint the code with flake8"
	@echo "  make run       - Run the application"
	@echo "  make clean     - Clean up temporary files"
	@echo "  make help      - Show this help message"
