import click
import os
import sys
from exec.executor import SeleniumThreadPoolExecutor
from utils.YouTubeScraper import YouTubeScraper

@click.group()
def cli():
    """CLI Tool for Selenium Executor and YouTube Scraper"""
    pass

@cli.command()
@click.option('--queries', multiple=True, default=["Read Dead Redemption", "God of War 2", "Mortal Kombat", "The Last of Us", "Yhwach vs Aizen", "Ichigo vs Aizen", "Aizen is the best"],
              help="List of search queries to scrape (use multiple options for multiple queries).")
@click.option('--max-cpu-count', default=3, type=int, help="Maximum number of CPU cores to use.")
@click.option('--max-cpu-usage', is_flag=True, default=False, help="Enable or disable max CPU usage limitation.")
def run_executor(queries, max_cpu_count, max_cpu_usage):
    """Run the SeleniumThreadPoolExecutor with YouTubeScraper"""
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
    
    click.echo("Preparing process pool...")
    executor.prepare_process_pool_and_implement()
    click.echo("Execution completed.")

if __name__ == "__main__":
    cli()