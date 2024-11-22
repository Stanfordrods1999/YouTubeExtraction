# YouTube Extraction Project

This project is designed to scrape YouTube search results programmatically using a multi-threaded Selenium-based scraper, `SeleniumThreadPoolExecutor`, and the `YouTubeScraper` class. It provides a CLI tool to execute the scraping process efficiently and handles tasks such as browser automation and data extraction.

---

## **Table of Contents**
1. [Features](#features)
2. [Setup Instructions](#setup-instructions)
3. [Project Structure](#project-structure)
4. [Usage](#usage)
5. [Testing](#testing)
6. [Troubleshooting](#troubleshooting)
7. [Contributing](#contributing)
8. [License](#license)

---

## **Features**

- **Multithreaded Scraping:** Uses `SeleniumThreadPoolExecutor` to run multiple scraping tasks concurrently.
- **Browser Automation:** Uses SeleniumBase with `undetected_chromedriver` to bypass bot detection.
- **Custom CLI Tool:** Execute scraping tasks with command-line arguments.
- **Flexible Configuration:** Supports passing custom search terms and options via CLI.
- **Robust Logging:** Tracks process execution and debugging outputs.

---

## **Setup Instructions**

### **1. Clone the Repository**
```bash
git clone https://github.com/yourusername/YouTubeExtraction.git
cd YouTubeExtraction
```

### **2. Install Dependencies**
This project uses Python 3.12 and requires `pip` and `virtualenv`.

```bash
python3 -m venv .venv
source .venv/bin/activate  # For Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### **3. Install Google Chrome and ChromeDriver**
- **Install Google Chrome:**
  ```bash
  wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo dpkg -i google-chrome-stable_current_amd64.deb
  sudo apt-get install -f -y
  ```
- **Install ChromeDriver:**
  Use SeleniumBase to install the appropriate version of ChromeDriver:
  ```bash
  sbase install chromedriver
  ```

---

## **Project Structure**

```
YouTubeExtraction/
├── utils/
│   ├── YouTubeScraper.py           # Class for scraping YouTube data
│   ├── __init__.py
├── exec/
│   ├── executor.py                 # Thread pool executor for managing scraping tasks
│   ├── __init__.py
├── tests/
│   ├── test_youtube_scraper.py     # Unit tests for YouTubeScraper
├── ScrapeRun.py                    # CLI entry point for the scraper
├── requirements.txt                # Project dependencies
├── Makefile                        # Build, test, and automation commands
├── README.md                       # Project documentation
```

---

## **Usage**

### **1. Run the CLI Tool**
Execute the scraper using the CLI tool. Replace the example queries with your own:
```bash
python src/ScrapeRun.py run-executor \
    --queries "Python programming tutorials" \
    --queries "Machine learning basics" \
    --max-cpu-count 4 \
    --max-cpu-usage
```

### **2. Use the Makefile**
The `Makefile` provides shortcuts for common tasks:

- **Run the scraper:**
  ```bash
  make run-scraper
  ```
- **Install dependencies:**
  ```bash
  make install
  ```
- **Test the project:**
  ```bash
  make test
  ```
- **Clean up:**
  ```bash
  make clean
  ```

---

## **Testing**

### **Run Unit Tests**
To test the functionality of the scraper:
```bash
pytest tests/test_youtube_scraper.py -v
```

### **Debugging**
Add breakpoints in your test script with `pdb`:
```python
import pdb; pdb.set_trace()
```

---

## **Troubleshooting**

1. **ChromeDriver Not Found:**
   Ensure `SELENIUMBASE_CHROME_DRIVER` is set correctly:
   ```bash
   export SELENIUMBASE_CHROME_DRIVER=/path/to/chromedriver
   ```

2. **Connection Refused Error:**
   - Ensure ChromeDriver and Chrome versions are compatible.
   - Update ChromeDriver:
     ```bash
     sbase install chromedriver
     ```

3. **Dependencies Not Installed:**
   Run:
   ```bash
   make install
   ```

---

## **Contributing**

Contributions are welcome! To contribute:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Open a pull request.

---

## **License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to modify and expand this `README.md` as your project evolves! Let me know if you’d like further customization. 🚀
