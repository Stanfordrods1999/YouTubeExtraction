import click
import os
import sys

# Add the parent directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SELENIUMBASE_CHROME_DRIVER"] = ".venv/bin/chromedriver"
os.environ["SELENIUMBASE_HEADLESS"] = "False"

from exec.executor import SeleniumThreadPoolExecutor
from utils.YouTubeScraper import YouTubeScraper

def test_run_executor():
    queries = ["Read Dead Redemption",
		 "God of War 2",
		 "Mortal Kombat",
		 "The Last of Us",
		 "Yhwach vs Aizen",
		 "Ichigo vs Aizen",
		 "Aizen is the best"]
    max_cpu_count = 4
    max_cpu_usage = None
    # Dynamically set the paths
    current_dir = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    lev_1 = os.path.dirname(current_dir)
    sys.path.append(lev_1)
    sys.path.append(os.path.dirname(lev_1))
    
    # Create and run the executor
    executor = SeleniumThreadPoolExecutor(
        list(queries),
        callable=YouTubeScraper,
        class_ref=True,
        func="scrape",
        max_cpu_count=max_cpu_count,
        max_cpu_usage=max_cpu_usage
    )
    
    print("Preparing process pool...")
    #executor.prepare_process_pool_and_implement()

    from seleniumbase import Driver

    data = executor.callable("Red Dead Redemption", Driver(incognito = True, uc = True ,multi_proxy = False), executor.lock)

    data.scrape()
    
    assert executor.callable == None
    print("Execution completed.")