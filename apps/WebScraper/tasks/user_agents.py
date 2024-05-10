import os
import random
import logging

# Initialize logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Global variable to store the user agents
user_agents = None


def get_user_agent():
    global user_agents
    # Load user agents if not already loaded
    if user_agents is None:
        user_agents = load_user_agents()
    return random.choice(user_agents)


def load_user_agents():
    logger.info("Loading user agents from file")
    file_path = "user-agents.txt"
    if not os.path.isabs(file_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, file_path)

    try:
        with open(file_path, "r") as file:
            user_agents = [line.strip() for line in file.readlines()]
            logger.debug(f"Loaded {len(user_agents)} user agents")
    except FileNotFoundError:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:54.0) Gecko/20100101 Firefox/54.0",
        ]
        logger.error("User agents file not found. Using default.")

    return user_agents

