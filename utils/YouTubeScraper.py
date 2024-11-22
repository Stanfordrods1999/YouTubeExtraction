from seleniumbase import Driver
from selenium.webdriver.common.by import By
import time
import json


class YouTubeScraper:
    def __init__(self, _data,driver,lock, scroll_attempts=3, scroll_pause=5):
        """
        Initializes the YouTubeScraper instance.
        
        :param search_query: The query to search on YouTube.
        :param scroll_attempts: Number of times to scroll for loading more results.
        :param scroll_pause: Pause time (in seconds) between each scroll.
        """
        self.search_query = _data
        self.driver = driver
        self.scroll_attempts = scroll_attempts
        self.scroll_pause = scroll_pause
        self.records = []

    def open_youtube(self):
        """Opens the YouTube homepage."""
        self.driver.get('https://www.youtube.com/')
        time.sleep(5)

    def search(self):
        """Performs a search for the specified query on YouTube."""
        search_box = self.driver.find_element(By.XPATH, '//input[@id="search"]')
        search_box.send_keys(self.search_query)
        search_button = self.driver.find_element(By.XPATH, '//button[@id="search-icon-legacy"]')
        search_button.click()

    def scroll_and_load(self):
        """Scrolls the page to load more results."""
        for _ in range(self.scroll_attempts):
            try:
                # Locate the continuation element for infinite scrolling
                continuation_element = self.driver.find_element(By.XPATH, '//ytd-continuation-item-renderer')
                # Scroll to the continuation element
                self.driver.execute_script("""
                    var element = arguments[0];
                    element.scrollIntoView({behavior: 'smooth', block: 'center'});
                """, continuation_element)
                time.sleep(self.scroll_pause)  # Pause to allow more results to load
            except Exception as e:
                print(f"Scroll failed: {e}")
                break

    def collect_video_data(self):
        """Collects video title and link data from the loaded results."""
        elements = self.driver.find_elements(By.XPATH, '//a[@id="video-title"]')
        # We can collect the data and decide where it should be put , 
        # since things are run parallely it's better to have them be sent to a database
        self.records = [{"Link": elem.get_attribute('href'), "Title": elem.get_attribute('title')} for elem in elements]

    def scrape(self):
        """
        Executes the full scraping process: open YouTube, search, scroll, and collect data.
        
        :return: List of dictionaries containing video titles and links.
        """
        self.open_youtube()
        self.search()
        time.sleep(3)  # Wait for the results to load
        self.scroll_and_load()
        self.collect_video_data()
        with open(f"./{self.search_query}_scrape.json", mode="w") as json_file:
            json.dump(self.records, json_file, indent=4)
