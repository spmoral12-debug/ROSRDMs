import os

brain = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a'

# Check file sizes
for fname in [
    'media_1794063646261_5f3d2736.jpg',
    'ros_redemption_splash_clean_1794018381576.jpg',
    'ros_redemption_tactical_sniper_clean_1794047799428.jpg',
    'ros_redemption_tactical_sniper_loading_1794047724623.jpg',
    'ros_redemption_loading_screen_1794018358520.jpg',
    'ros_redemption_login_clean_1794046745388.jpg'
]:
    p = os.path.join(brain, fname)
    if not os.path.exists(p):
        p = os.path.join(brain, '.user_uploaded', fname)
    if os.path.exists(p):
        print(f"{fname:55} size={os.path.getsize(p)}")

