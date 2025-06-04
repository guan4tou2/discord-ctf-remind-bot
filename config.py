import os

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Discord Bot 配置
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("未设置 DISCORD_TOKEN 环境变量")

# 可选：Discord 服务器 ID（用于限制命令在特定服务器中使用）
GUILD_ID = os.getenv("GUILD_ID")
if GUILD_ID:
    GUILD_ID = int(GUILD_ID)
