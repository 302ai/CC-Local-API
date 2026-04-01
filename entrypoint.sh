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

# 恢复 acpx skill 与文档（避免被挂载覆盖；并修正 acpx skill 路径）
mkdir -p /home/user/.claude/skills/acpx
if [ -f /app/.acpx-backup/skills/acpx/SKILL.md ]; then
  cp -a /app/.acpx-backup/skills/acpx/SKILL.md /home/user/.claude/skills/acpx/SKILL.md
  echo "Restored acpx SKILL.md -> /home/user/.claude/skills/acpx/SKILL.md"
fi

mkdir -p /home/user/acpx/docs
if [ -f /app/.acpx-backup/docs/CLI.md ]; then
  cp -a /app/.acpx-backup/docs/CLI.md /home/user/acpx/docs/CLI.md
  echo "Restored acpx CLI.md -> /home/user/acpx/docs/CLI.md"
fi

# 启动服务
openclaw gateway run --port 18789 --bind lan &
uvicorn main:app --host 0.0.0.0 --port 8000
