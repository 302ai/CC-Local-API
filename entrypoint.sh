#!/bin/bash

# 恢复插件（只替换备份中存在的，不影响用户自装的插件）
mkdir -p /home/user/.openclaw/extensions
for p in /app/.openclaw-extensions-backup/extensions/*; do
  name="$(basename "$p")"
  rm -rf "/home/user/.openclaw/extensions/$name"
  cp -a "$p" /home/user/.openclaw/extensions/
  echo "Restored openclaw extension (overwrite): $name"
done
chmod -R 755 /home/user/.openclaw

# 恢复 skills
mkdir -p /home/user/.claude/skills
for p in /app/.skills-backup/*; do
  name="$(basename "$p")"
  cp -a "$p" /home/user/.claude/skills/ 2>/dev/null || true
  echo "Restored skill entry (overwrite): $name"
done

# 启动服务
openclaw gateway run --port 18789 --bind lan &
uvicorn main:app --host 0.0.0.0 --port 8000
