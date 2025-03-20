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
	--queries "Latest Bollywood news today" \
	--queries "Upcoming Indian movies 2025" \
	--queries "Top South Indian movies this year" \
	--queries "Best Hindi web series 2025" \
	--queries "Trending Bollywood songs 2025" \
	--queries "Best Indian rap songs this year" \
	--queries "Latest cricket updates India" \
	--queries "IPL 2025 latest news" \
	--queries "Top Indian gaming YouTubers" \
	--queries "Most popular Indian streamers 2025" \
	--queries "Best Indian PC games" \
	--queries "Upcoming Indian gaming tournaments" \
	--queries "Indian historical documentaries" \
	--queries "Mughal Empire history in Hindi" \
	--queries "Shivaji Maharaj full history" \
	--queries "Ancient Indian warfare techniques" \
	--queries "Latest Indian tech startups" \
	--queries "Best Indian smartphones 2025" \
	--queries "Latest budget phones in India" \
	--queries "India’s space mission updates" \
	--queries "ISRO upcoming missions" \
	--queries "Most viral Indian memes" \
	--queries "Trending Indian Instagram reels" \
	--queries "Best Indian stand-up comedians" \
	--queries "Latest political news India" \
	--queries "Top Indian stock market trends" \
	--queries "Best investment options in India 2025" \
	--queries "Top government job exams 2025" \
	--queries "Best engineering colleges in India" \
	--queries "Best MBA colleges in India 2025" \
	--queries "How to get a job in India 2025" \
	--queries "Indian eSports scene 2025" \
	--queries "Best Indian AI startups" \
	--queries "Top tech jobs in India 2025" \
	--queries "Best Indian coding bootcamps" \
	--queries "Best Indian historical podcasts" \
	--queries "Latest mythological TV shows India" \
	--queries "Indian history facts you didn't know" \
	--queries "Best Indian war movies" \
	--queries "Underrated Indian movies 2025" \
	--queries "Top Indian horror movies 2025" \
	--queries "Best Indian comedy movies" \
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
