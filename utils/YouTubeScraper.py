from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import re 
from datetime import datetime, timedelta


## TODO: Create a WebDriverWait for soem fo the interactable elements 
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
        self.wait = WebDriverWait(self.driver,10)
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

    def extract_metadata_from_text(self,title:str,aria_label:str):
        """Right now this is the easiest way to do it without needing to open the link"""
        aria_label = aria_label.replace(title+" by",'')
        aria_label  = aria_label.split(' ')
        channel = ""
        views = ""
        for i in range(len(aria_label)):
            if(aria_label[i] == "views"):
                views = aria_label[i-1]
                channel = ' '.join(aria_label[:i-1])
                time = self.convert_relative_time_to_datetime(' '.join(aria_label[i+1:]))
                break
        return {"YT_Channel":channel,"YT_Views":views,"YT_Time":time}    
    
    def convert_relative_time_to_datetime(self,relative_time: str):
        """Convert a relative time string into an absolute datetime."""
        now = datetime.now()
        time_delta = timedelta()

        # Extract numbers and units using regex
        matches = re.findall(r"(\d+)\s+(hour|minute|day|week|month|year)s?", relative_time)

        for value, unit in matches:
            value = int(value)
            if unit == "minute":
                time_delta += timedelta(minutes=value)
            elif unit == "hour":
                time_delta += timedelta(hours=value)
            elif unit == "day":
                time_delta += timedelta(days=value)
            elif unit == "week":
                time_delta += timedelta(weeks=value)
            elif unit == "month":
                time_delta += timedelta(days=30 * value)  # Approximation
            elif unit == "year":
                time_delta += timedelta(days=365 * value)  # Approximation

        # Subtract the timedelta from now to get the absolute time
        absolute_time = now - time_delta
        return absolute_time.strftime("%m/%d/%Y, %H:%M:%S")

    def collect_video_data(self):
        """Collects video title and link data from the loaded results."""
        elements = self.driver.find_elements(By.XPATH, '//a[@id="video-title"]')

        # We can collect the data and decide where it should be put , 
        # since things are run parallely it's better to have them be sent to a database
        for elem in elements:
            # Extract title and aria-label
            title = elem.get_attribute('title')
            aria_label = elem.get_attribute('aria-label')
            link = elem.get_attribute('href')
            
            # Collect metadata
            metadata = self.extract_metadata_from_text(title, aria_label)
            
            # Combine the collected data
            record = {
                "Search_Query": self.search_query,
                "Link": link,
                "Title": title
            }
            # Update the record with extracted metadata
            record.update(metadata)
            
            # Append the record to the records list
            self.records.append(record)

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
