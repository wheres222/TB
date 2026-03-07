"""
Test script to verify all modules can be imported successfully
Run this before starting the bot to catch any import errors
"""

import sys

def test_imports():
    """Test that all modules can be imported"""
    print("Testing module imports...\n")
    
    modules = [
        'welcome_system',
        'invite_detection',
        'message_logger',
        'account_monitoring',
        'enhanced_achievements',
        'channel_analytics',
        'business_features',
        'schema_updates'
    ]
    
    failed = []
    
    for module_name in modules:
        try:
            __import__(module_name)
            print(f"✓ {module_name}")
        except Exception as e:
            print(f"✗ {module_name}: {e}")
            failed.append(module_name)
    
    print("\n" + "="*50)
    
    if failed:
        print(f"❌ {len(failed)} module(s) failed to import:")
        for module in failed:
            print(f"  - {module}")
        print("\nPlease fix these errors before running the bot.")
        return False
    else:
        print("✅ All modules imported successfully!")
        print("You can now run the bot with: python bot.py")
        return True

def test_dependencies():
    """Test that required dependencies are installed"""
    print("\nTesting dependencies...\n")
    
    dependencies = [
        ('discord', 'discord.py'),
        ('aiosqlite', 'aiosqlite'),
        ('dotenv', 'python-dotenv')
    ]
    
    failed = []
    
    for module, package in dependencies:
        try:
            __import__(module)
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} - NOT INSTALLED")
            failed.append(package)
    
    print("\n" + "="*50)
    
    if failed:
        print(f"❌ {len(failed)} dependency(ies) missing:")
        for package in failed:
            print(f"  - {package}")
        print("\nInstall with: pip install -r requirements.txt")
        return False
    else:
        print("✅ All dependencies installed!")
        return True

def test_env_file():
    """Test that .env file exists and has token"""
    print("\nTesting configuration...\n")
    
    import os
    from pathlib import Path
    
    env_file = Path('.env')
    
    if not env_file.exists():
        print("✗ .env file not found")
        print("\nCreate .env file with your bot token:")
        print("  1. Copy .env.example to .env")
        print("  2. Add your Discord bot token")
        return False
    
    print("✓ .env file exists")
    
    # Try to load it
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        token = os.getenv('DISCORD_TOKEN')
        if not token or token == 'your_bot_token_here':
            print("✗ DISCORD_TOKEN not set in .env file")
            print("\nEdit .env and add your actual bot token")
            return False
        
        print("✓ DISCORD_TOKEN configured")
        print("\n" + "="*50)
        print("✅ Configuration looks good!")
        return True
        
    except Exception as e:
        print(f"✗ Error loading .env: {e}")
        return False

def main():
    """Run all tests"""
    print("="*50)
    print("Discord Bot Pre-Flight Check")
    print("="*50 + "\n")
    
    deps_ok = test_dependencies()
    if not deps_ok:
        print("\n⚠️  Fix dependency issues first, then run this script again.")
        sys.exit(1)
    
    imports_ok = test_imports()
    if not imports_ok:
        print("\n⚠️  Fix import issues first, then run this script again.")
        sys.exit(1)
    
    config_ok = test_env_file()
    if not config_ok:
        print("\n⚠️  Fix configuration issues first, then run this script again.")
        sys.exit(1)
    
    print("\n" + "="*50)
    print("🎉 All checks passed! Ready to start bot.")
    print("="*50)
    print("\nRun the bot with:")
    print("  Windows: run.bat")
    print("  Linux/Mac: ./run.sh")
    print("  Direct: python bot.py")

if __name__ == "__main__":
    main()
