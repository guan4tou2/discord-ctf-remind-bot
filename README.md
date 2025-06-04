# Discord CTF 比赛提醒机器人

这是一个用于管理 CTF 比赛的 Discord 机器人，可以帮助团队成员追踪和参与 CTF 比赛。

## 功能特点

1. 从 CTFtime 获取比赛信息
2. 手动添加 CTF 比赛
3. 支持团队成员加入比赛
4. 自动发送比赛开始和结束提醒

## 安装步骤

1. 克隆此仓库
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 创建 `.env` 文件并添加你的 Discord bot token：
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   ```

## 使用方法

1. 启动机器人：
   ```bash
   python main.py
   ```

2. 可用命令：
   - `!add_ctf <比赛名称> <开始时间> <结束时间> [比赛链接]` - 添加新的 CTF 比赛
   - `!list_ctf` - 列出所有 CTF 比赛

## 注意事项

- 时间格式必须为：YYYY-MM-DD HH:MM
- 机器人会提前 1 小时发送比赛开始和结束提醒
- 确保机器人有足够的权限来发送消息和查看频道
