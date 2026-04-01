"""
Multi-Bot Launcher
==================

Launches all CellClaw bots for the multi-agent chat system.

Usage:
    python main_multi.py [bot_name]
    
    bot_name: orchestrator, planner, coder, reviewer, executor
    If not specified, launches all bots.
"""

import asyncio
import logging
import os
import sys
import signal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bots.orchestrator_bot import OrchestratorBot, create_orchestrator_bot
from bots.planner_bot import PlannerBot, create_planner_bot
from bots.coder_bot import CoderBot, create_coder_bot
from bots.reviewer_bot import ReviewerBot, create_reviewer_bot
from bots.executor_bot import ExecutorBot, create_executor_bot


# Logger setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# Global bot instances
bots = {}


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("Received shutdown signal...")
    for name, bot in bots.items():
        logger.info(f"Closing {name}...")
        # In production, would call bot.close()
    sys.exit(0)


def list_bots():
    """List available bots."""
    print("""
CellClaw Multi-Bot System
=========================

Available bots:
  orchestrator  - Task coordinator (receives tasks from leader)
  planner       - Creates execution plans
  coder         - Generates code
  reviewer      - Reviews generated code
  executor      - Executes tasks on remote servers
  all           - Launch all bots (default)

Usage:
  python main_multi.py [bot_name]

Example:
  python main_multi.py orchestrator
  python main_multi.py all
""")


async def run_bot(bot_class, create_fn, name: str):
    """Run a single bot."""
    logger.info(f"Starting {name} bot...")
    
    try:
        bot = create_fn()
        bots[name] = bot
        await bot.run()
    except KeyboardInterrupt:
        logger.info(f"{name} bot stopped by user")
    except Exception as e:
        logger.error(f"{name} bot error: {e}")
        raise


async def main():
    """Main entry point."""
    # Get bot name from args
    bot_name = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    
    if bot_name == "list":
        list_bots()
        return
    
    logger.info(f"Launching CellClaw Multi-Bot System: {bot_name}")
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Launch requested bots
    if bot_name == "orchestrator":
        await run_bot(OrchestratorBot, create_orchestrator_bot, "orchestrator")
    
    elif bot_name == "planner":
        await run_bot(PlannerBot, create_planner_bot, "planner")
    
    elif bot_name == "coder":
        await run_bot(CoderBot, create_coder_bot, "coder")
    
    elif bot_name == "reviewer":
        await run_bot(ReviewerBot, create_reviewer_bot, "reviewer")
    
    elif bot_name == "executor":
        await run_bot(ExecutorBot, create_executor_bot, "executor")
    
    elif bot_name == "all":
        # Run all bots concurrently
        tasks = [
            run_bot(OrchestratorBot, create_orchestrator_bot, "orchestrator"),
            run_bot(PlannerBot, create_planner_bot, "planner"),
            run_bot(CoderBot, create_coder_bot, "coder"),
            run_bot(ReviewerBot, create_reviewer_bot, "reviewer"),
            run_bot(ExecutorBot, create_executor_bot, "executor"),
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    else:
        logger.error(f"Unknown bot: {bot_name}")
        list_bots()


if __name__ == "__main__":
    asyncio.run(main())
