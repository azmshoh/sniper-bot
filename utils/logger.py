import logging
import os
from datetime import datetime

def setup_logger(log_file: str, log_format: str):
    """Setup logging configuration"""
    
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{timestamp}_{log_file}")
    
    # Setup logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    # Log startup information
    logging.info("Bot started")
    logging.info(f"Log file: {log_file}")
    
    # Log environment check
    if not os.getenv('PRIVATE_KEY'):
        logging.error("PRIVATE_KEY not found in environment variables!")
    else:
        logging.info("PRIVATE_KEY found in environment variables")