import argparse
import asyncio
import sys
import os
from aiohttp import web
from bot import create_bot
import sqlite3
from constants import DB_PATH, CONFIG_PATH, DEFAULT_CONFIG
from utils.config import save_config, load_config
import logging
from dotenv import load_dotenv


#listen for health checks (for Cloud Run)
async def health_check():
    app = web.Application()
    
    # Rate limiting middleware
    @web.middleware
    async def rate_limit(request, handler):
        ip = request.remote
        if hasattr(app, 'ip_count'):
            if ip in app.ip_count and app.ip_count[ip] > 100:  # 100 requests per minute
                return web.Response(status=429)
            app.ip_count[ip] = app.ip_count.get(ip, 0) + 1
        return await handler(request)
    
    app.middlewares.append(rate_limit)
    app.ip_count = {}
    
    async def handle(request):
        return web.Response(text="OK")
    
    # Only bind to localhost in development
    host = '127.0.0.1' if os.getenv('ENVIRONMENT') == 'development' else '0.0.0.0'
    
    app.router.add_get("/health", handle)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, int(os.getenv('PORT', 8080)))
    await site.start()

    # Reset rate limits every minute
    while True:
        await asyncio.sleep(60)
        app.ip_count.clear()

async def run_headless():
    
    # Set up logging for headless mode
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)
    """Run the bot in headless mode without GUI"""

    try:
        # Initialize database connection
        con = sqlite3.connect(DB_PATH)
        
        # Create bot instance
        bot = create_bot(con)
        
        # Load config
        config = DEFAULT_CONFIG.copy()
        if not os.path.exists(CONFIG_PATH):
            save_config(CONFIG_PATH, DEFAULT_CONFIG)
        else:
            config = load_config(CONFIG_PATH)

        # Load token from dotenv, if exists
        load_dotenv()

        # Get token from environment or config
        bot_token = os.getenv('BOT_TOKEN') or config.get('bot_token')
        if not bot_token:
            raise ValueError("Bot token not found. Set BOT_TOKEN environment variable or configure in config.json")
        else:
            config.setdefault('bot_token', bot_token)

        # Start health check server for Cloud Run
        asyncio.create_task(health_check())

        # Start the bot
        await bot.start(bot_token)
        
    except Exception as e:
        print(f"Error in headless mode: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Danisen Bot')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode without GUI')
    args = parser.parse_args()

    if args.headless:
        asyncio.run(run_headless())
    else:
        from PyQt6.QtWidgets import QApplication
        from gui import DanisenWindow
        import qasync

        app = QApplication(sys.argv)
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        window = DanisenWindow()
        window.show()
        
        with loop:
            loop.run_forever()

if __name__ == '__main__':
    main()