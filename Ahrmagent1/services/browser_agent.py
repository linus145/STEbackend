import asyncio
from playwright.async_api import async_playwright
from django.conf import settings
from Ahrmagent1.models import AgentExecution, AgentLog
import time
import os
import sys

# Critical fix for Playwright on Windows
if sys.platform == 'win32':
    try:
        asyncio.get_event_loop_policy()
        if not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class BrowserAgentService:
    """
    Base service for browser automation using Playwright.
    Handles browser lifecycle, navigation, and common actions.
    """
    
    def __init__(self, execution_id=None):
        self.execution = None
        if execution_id:
            self.execution = AgentExecution.objects.get(id=execution_id)
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    async def start_browser(self, headless=True, slow_mo=500, use_existing=False, use_persistent=True):
        self.playwright = await async_playwright().start()
        
        if use_existing:
            self.log("Attempting to connect to your open browser (127.0.0.1:9222)...", action="connect_browser")
            for attempt in range(3):
                try:
                    self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    if self.browser.contexts:
                        self.context = self.browser.contexts[0]
                        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                    else:
                        self.context = await self.browser.new_context()
                        self.page = await self.context.new_page()
                    self.log("Connected to your browser successfully!", action="connect_success")
                    return
                except Exception as e:
                    if attempt < 2:
                        self.log(f"Attempt {attempt + 1} failed. Retrying in 2s...")
                        await asyncio.sleep(2)
                    else:
                        raise ConnectionError(
                            "Could not connect to your browser. \n"
                            "1. Ensure Chrome is COMPLETELY closed first.\n"
                            "2. Run the PowerShell command again.\n"
                            "3. Verify by visiting http://127.0.0.1:9222/json in Chrome."
                        )
        
        if use_persistent:
            # Persistent context keeps you logged in!
            user_data_dir = os.path.join(settings.BASE_DIR, 'agent_user_data')
            os.makedirs(user_data_dir, exist_ok=True)
            self.log(f"Starting browser with persistent context at {user_data_dir}", action="start_persistent")
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir,
                headless=headless,
                slow_mo=slow_mo,
                args=['--remote-debugging-port=9222'] # Enable debugging on the browser we launch!
            )
            self.browser = None # In persistent mode, the context IS the browser handle
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        else:
            self.browser = await self.playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            self.log("New browser started successfully", action="start_browser")

    async def close_browser(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        await self.stop_playwright()

    async def stop_playwright(self):
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
            self.playwright = None
        self.log("Playwright driver stopped", action="stop_driver")

    async def navigate(self, url):
        self.log(f"Navigating to {url}", action="navigate")
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

    async def fill_field(self, selector, value):
        self.log(f"Filling {selector} with value", action="fill")
        await self.page.wait_for_selector(selector)
        await self.page.focus(selector)
        await self.page.fill(selector, value)
        # Dispatch input event manually for React
        await self.page.evaluate(f'document.querySelector("{selector}").dispatchEvent(new Event("input", {{ bubbles: true }}))')

    async def type_text(self, selector, value, delay=100):
        self.log(f"Typing into {selector}", action="type")
        await self.page.wait_for_selector(selector)
        await self.page.click(selector) # Focus
        await self.page.type(selector, value, delay=delay)

    async def click_element(self, selector):
        self.log(f"Clicking {selector}", action="click")
        await self.page.wait_for_selector(selector)
        await self.page.click(selector)

    async def take_screenshot(self, name="screenshot"):
        filename = f"{name}_{int(time.time())}.png"
        path = os.path.join(settings.MEDIA_ROOT, 'agent_screenshots', filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await self.page.screenshot(path=path)
        self.log(f"Screenshot saved as {filename}", action="screenshot")
        
        if self.execution:
            def save_screenshot():
                self.execution.screenshot = f"agent_screenshots/{filename}"
                self.execution.save()
            
            from asgiref.sync import sync_to_async
            await sync_to_async(save_screenshot, thread_sensitive=False)()
        return filename

    def log(self, message, level="INFO", action=None):
        print(f"[{level}] {message}")
        if self.execution:
            from asgiref.sync import async_to_sync, sync_to_async
            import asyncio

            def save_log():
                AgentLog.objects.create(
                    execution=self.execution,
                    level=level,
                    message=message,
                    action=action
                )
                if action:
                    self.execution.actions_performed.append({
                        "action": action,
                        "message": message,
                        "timestamp": time.time()
                    })
                    self.execution.save()

            # Detect if we are in an async loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Set thread_sensitive=False to prevent deadlocks with CurrentThreadExecutor
                    asyncio.create_task(sync_to_async(save_log, thread_sensitive=False)())
                else:
                    save_log()
            except RuntimeError:
                save_log()
