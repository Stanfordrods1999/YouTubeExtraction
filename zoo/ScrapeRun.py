import os 
import sys 
current_dir = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
lev_1 = os.path.dirname(current_dir)
print(lev_1)
sys.path.append(lev_1)
sys.path.append(os.path.dirname(lev_1))
from exec.executor import SeleniumThreadPoolExecutor
from utils.YouTubeScraper import YouTubeScraper


executor = SeleniumThreadPoolExecutor(["Read Dead Redemption","God of War 2","Mortal Kombat","The Last of Us","Yhwach vs Aizen","Ichigo vs Aizen","Aizen is the best"],callable=YouTubeScraper,class_ref=True,func="scrape",max_cpu_count=3,max_cpu_usage=False)

executor.prepare_process_pool_and_implement()