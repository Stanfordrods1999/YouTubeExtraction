# Variables
PYTHON = python3.12
VENV_DIR = .venv
CHROME_DRIVER_DIR = $(VENV_DIR)/bin
SELENIUMBASE_DRIVER_DIR = $(VENV_DIR)/lib/$(PYTHON)/site-packages/seleniumbase/drivers
CHROME_DRIVER_PATH = $(CHROME_DRIVER_DIR)/chromedriver
CLI_TOOL = ScrapeRun

.PHONY: all install install-chromedriver set-env test lint run-scraper clean

# Default target
all: install

# Create a virtual environment and install dependencies
$(VENV_DIR):
	$ python -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip

install: $(VENV_DIR)
	$(VENV_DIR)/bin/pip install -r requirements.txt

# Install Google Chrome
install-chrome:
	@echo "Installing Google Chrome..."
	@if [ `uname` = "Linux" ]; then \
		wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O chrome.deb; \
		sudo apt-get update; \
		sudo apt-get install -y fonts-liberation libvulkan1 xdg-utils; \
		sudo dpkg -i chrome.deb || sudo apt-get install -f -y; \
		rm -f chrome.deb; \
	elif [ `uname` = "Darwin" ]; then \
		echo "Please install Chrome manually on macOS."; \
	else \
		echo "Please install Chrome manually on Windows."; \
	fi

# Install ChromeDriver
install-chromedriver:
	@echo "Installing ChromeDriver via SeleniumBase..."
	$(VENV_DIR)/bin/pip install seleniumbase
	$(VENV_DIR)/bin/sbase install chromedriver
	@echo "Detecting ChromeDriver path..."
	CHROME_DRIVER_PATH=`find $(SELENIUMBASE_DRIVER_DIR) -name chromedriver | head -n 1`; \
	if [ -z "$$CHROME_DRIVER_PATH" ]; then \
		echo "ChromeDriver not found! Please ensure it is installed."; \
	else \
		echo "ChromeDriver installed at: $$CHROME_DRIVER_PATH"; \
		ln -sf $$CHROME_DRIVER_PATH $(CHROME_DRIVER_DIR)/chromedriver; \
	fi

# Run tests using pytest
test:
	$(VENV_DIR)/bin/pytest tests/test_execdata.py --pdb

# Lint the code using flake8
lint:
	$(VENV_DIR)/bin/flake8 src tests

# Run the ScrapeRun CLI tool
run-scraper:
	SELENIUMBASE_CHROME_DRIVER=$(CHROME_DRIVER_PATH) \
	SELENIUMBASE_HEADLESS="False" \
	$(VENV_DIR)/bin/python $(CLI_TOOL).py run-executor \
	--queries "Trending news worldwide today" \
	--queries "Latest viral videos 2025" \
	--queries "Top trending topics this week" \
	--queries "YouTube trending videos [your country]" \
	--queries "Latest AI breakthroughs 2025" \
	--queries "Top programming languages 2025" \
	--queries "Best AI tools for developers" \
	--queries "Machine learning trends this year" \
	--queries "Top upcoming games 2025" \
	--queries "Best indie games of the year" \
	--queries "Most popular gaming trends 2025" \
	--queries "Trending gaming news today" \
	--queries "Stock market updates today" \
	--queries "Latest crypto news 2025" \
	--queries "Business trends 2025" \
	--queries "Best investments this year" \
	--queries "Top universities for machine learning" \
	--queries "Best certifications for tech jobs 2025" \
	--queries "Highest paying tech jobs this year" \
	--queries "Best strategies for getting into top colleges" \
	--queries "Aurangzeb history documentary" \
	--queries "Shivaji vs Aurangzeb real story" \
	--queries "Mughal Empire in 17th century" \
	--queries "Historical battles of the Mughal era"
	--max-cpu-count 8

# Clean up temporary files and virtual environment
clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	rm -rf *.json
	rm -rf $(VENV_DIR)
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .coverage
	rm -rf htmlcov
