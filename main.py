# main.py
import time
from engine import ADBController
import config

def main():
    print("🚀 Starting MarineoClash Lite...")
    bot = ADBController()

    if not bot.check_connection():
        return

    # --- MAIN LOOP ---
    while True:
        print("\n--- New Cycle ---")
        
        # 1. Collect Resources
        print("Collecting resources...")
        bot.tap(*config.BTN_COLLECT_ALL)
        time.sleep(2)

        # 2. Start Attack Search
        print("Searching for opponent...")
        bot.tap(*config.BTN_ATTACK)
        time.sleep(5)

        # 3. Find Match (Loop until we find one or give up)
        # For now, we just click 'Next' a few times to simulate searching
        for i in range(3):
            print(f"Checking opponent {i+1}...")
            time.sleep(2) 
            # In a real bot, you would use OpenCV here to analyze the screenshot
            # to see if the loot is good. For now, we just click Next.
            bot.tap(*config.BTN_NEXT_OPPONENT)
            time.sleep(3)

        # 4. Attack (Blindly for this example)
        print("Deploying troops...")
        bot.tap(*config.BTN_GO)
        
        # Wait for battle to end
        print(f"Waiting {config.TIME_TO_WAIT_FOR_BATTLE} seconds for battle...")
        time.sleep(config.TIME_TO_WAIT_FOR_BATTLE)

        # 5. Return Home
        print("Returning home...")
        bot.tap(*config.BTN_RETURN_HOME)
        time.sleep(5)

        print("Cycle complete. Sleeping...")
        time.sleep(config.TIME_BETWEEN_ATTACKS)

if __name__ == "__main__":
    main()
