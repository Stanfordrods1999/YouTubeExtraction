import sys
import os 

current_dir = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
lev_1 = os.path.dirname(current_dir)
sys.path.append(lev_1)

from logs.Logging import Logging
import multiprocessing as mp
from threading import Lock,Thread 

from seleniumbase import Driver


log = Logging(os.path.splitext(os.path.basename(__file__))[0])

import os
from seleniumbase import Driver

def initialize_driver():
    """
    Initialize the SeleniumBase Driver with dynamically determined paths.
    Uses environment variables set by the Makefile for ChromeDriver configuration.
    """
    # Get the ChromeDriver path from the environment variable
    chrome_driver_path = os.getenv("SELENIUMBASE_CHROME_DRIVER")
    if not chrome_driver_path:
        raise EnvironmentError("ChromeDriver path is not set. Ensure SELENIUMBASE_CHROME_DRIVER is configured.")

    # Initialize the SeleniumBase Driver
    driver = Driver(
        incognito=True,  # Open browser in incognito mode
        uc=True,         # Use undetected Chrome for bot prevention
        multi_proxy=True # Enable multiple proxy support
    )
    return driver

 
class SeleniumThreadPoolExecutor:
    """
    1. **Persistent Selenium Drivers**:
       - Eliminates the need to repeatedly initialize and close Selenium drivers for every task.
       - Reduces overhead and improves performance.

    2. **Thread-Based Concurrency**:
       - Utilizes a thread pool to assign tasks to Selenium drivers in parallel.
       - Allows efficient use of system resources while avoiding excessive driver instances.

    3. **Lock Mechanism**:
       - Implements a lock for communication between scrapers, there were certain interactions that needed this.
       - Ensures thread safety and prevents race conditions.
    
    4. **Task Queue Management**:
       - Uses multiprocessing queues to manage incoming tasks and distribute them among available workers.
       - Ensures seamless task delegation and completion tracking.

    5. **Class Reference Integration**:
       - Done this because I have this inherent need as a long time Java Developer to put everything into a class
       - Supports passing a callable class reference (`class_ref`) to allow method-based scraping workflows.
       - Dynamically invokes the specified method on the class instance for each task.
       - TODO:I've stupidly implemented the way this task is supposed to be called, if a function is provided along with a callable, it is a class
         do not need the class_ref variable  

    **Usage**:
    - Instantiate with a list of URLs and a callable function or class reference.
    - TODO: Here is where the stupidity comes in , you need to pass class_ref as true, which is not needed , also if 
    max_cpu_count is provided then max_cpu_usage does not need to be provided , if no max_cpu_count is provided then use all the drivers 
    - Call `prepare_process_pool_and_implement()` to start the scraping process.
    """

    def __init__(self,url_list,callable,class_ref=False,max_cpu_usage:bool = True,max_cpu_count:int = None,**callable_kwargs) -> None:
        self.url_list = url_list
        self.max_cpu_count = max_cpu_count
        self.max_cpu_usage = max_cpu_usage
        self.callable = callable
        self.class_ref = class_ref
        self.lock  = Lock()
        self.flag = True
        self.func = callable_kwargs.pop('func')
        #print(callable_kwargs.pop('func'))
        self.func_kwargs = callable_kwargs
        self.driver = initialize_driver()
        
        
    def selenium_queue_listener(self,data_queue: mp.Queue, worker_queue: mp.Queue, selenium_workers: dict):
        """Listens to the Selenium data queue, assigns tasks to workers, and collects results.

        Args:
            data_queue (mp.Queue): Queue for passing data to be processed by Selenium.
            worker_queue (mp.Queue): Queue to manage available worker IDs.
            selenium_workers (dict): Dictionary mapping worker IDs to Selenium instances.

        Returns:
            None"""
        while True:
                    
            # Get data and worker ID from the queues
            _data = data_queue.get()
            
            # Check if the data queue is empty
            if _data == "STOP":
                log.logger.warning("STOP encountered, kill the worker thread")
                data_queue.put(_data)
                break
            else:
                log.logger.info(f"Got the processing data {_data} on the data queue")
            worker_id = worker_queue.get()
            log.logger.info(f"{worker_id}")
            # Get the Selenium worker instance for the current task
            worker = selenium_workers[worker_id]
            
            if self.class_ref:
                class_instance = self.callable(_data = _data , driver=worker, lock=self.lock)
                method = getattr(class_instance,self.func)
                method()
                 
            else:
                self.callable(_data = _data, driver=worker, lock=self.lock)
            # Put the worker back into the worker queue as it has completed its task
            worker_queue.put(worker_id)
        return 
    
    def prepare_process_pool_and_implement(self):
        """
        Prepare a process pool for web scraping tasks and implement scraping.

        Args:
            url_list (list): List of URLs to scrape.
            max_cpu_usage (bool): Use all available CPU cores if True (default).
            max_cpu_count (int): Maximum number of CPU cores to use if max_cpu_usage is False.

        Returns:
            multiprocessing.Queue: A queue for passing data between Selenium and worker processes.
        """
    
        self.url_list.append("STOP")
        # Initialize queues for data communication
        selenium_data_queue = mp.Queue()
        worker_data_queue = mp.Queue()
        
        if self.max_cpu_usage:
            # Use all available CPU cores
            worker_ids = list(range(mp.cpu_count()))
        else:
            if self.max_cpu_count is not None:
                # Use a specific number of CPU cores
                worker_ids = list(range(self.max_cpu_count))
            else:
                raise ValueError("max_cpu_usage is set to False, please provide max_cpu_count.")
        
        # Create a dictionary to map worker IDs to Selenium instances
        selenium_workers = {i: self.driver for i in worker_ids}
        
        for worker_id in worker_ids:
            worker_data_queue.put(worker_id)
        
        
        # Create a list of threads for Selenium processing
        selenium_processes = [Thread(target=self.selenium_queue_listener,
                                    args=(selenium_data_queue, worker_data_queue, selenium_workers)) for _ in worker_ids]
        
        # Start the Selenium processing threads
        for p in selenium_processes:
            p.daemon = True
            p.start()
            
        # Queue up the URLs for processing
        for url in self.url_list:
            selenium_data_queue.put(url)

        # Wait for all threads to complete
        for p in selenium_processes:
            p.join()
        
        # Quit the Selenium instance
        for workers in selenium_workers.values():
            workers.quit()