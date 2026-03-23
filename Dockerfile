FROM python:3.12-slim

# 合并所有 apt 操作到一个 RUN，并清理缓存
RUN apt-get update && apt-get install -y --no-install-recommends \
  libmagic1 \
  git \
  sudo \
  curl \
  gnupg \
  zip \
  ca-certificates \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && npm install -g @anthropic-ai/claude-code@latest \
  && npm install -g openclaw@latest \
  && npm install -g clawhub@latest \
  && npm install -g @playwright/cli@latest \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && rm -rf /root/.npm \
  && rm -rf /tmp/*

# 创建用户
RUN groupadd -r user && useradd -r -g user -m -s /bin/bash user

# 创建目录并设置权限
RUN mkdir -p /data /data/user /app /home/user/.claude/skills /home/user/.openclaw /home/user/db && \
    chown -R user:user /data /app /home/user && \
    chmod 755 /data /app /home/user && \
    chmod 775 /home/user/db /home/user/.claude /home/user/.claude/skills && \
    chmod -R 755 /home/user/.openclaw


# 安装 Python 依赖
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY --chown=user:user . /app

# 复制自定义 skills 到不会被挂载覆盖的目录
COPY --chown=user:user skills/ /app/.skills-backup/

ENV HOME=/home/user

EXPOSE 8000 18789

# 启动时尝试修复挂载目录权限（bind mount 场景可能无效），然后降权运行主命令
ENTRYPOINT ["sh", "-lc", "\
    set -e && \
    echo 'BOOT: entrypoint start' && \
    mkdir -p /home/user/.openclaw /home/user/db && \
    chmod -R 755 /home/user/.openclaw 2>/dev/null || true && \
    chown -R user:user /home/user/.openclaw 2>/dev/null || true && \
    chown -R user:user /home/user/db 2>/dev/null || true && \
    chmod 755 /home/user/db 2>/dev/null || true && \
    exec su -s /bin/sh -c \"$*\" user --\
", "--"]

# 启动时检查 channels 插件是否存在，不存在才恢复
CMD ["sh", "-c", "\
    set -e && \
    echo 'BOOT: cmd start' && \
    OPENCLAW_CFG=\"/home/user/.openclaw/openclaw.json\" && \
    OPENCLAW_CFG_BAK=\"/home/user/.openclaw/openclaw.json.back302ai\" && \
    CHANNELS_DIR=\"/home/user/.openclaw/extensions/channels\" && \
    if [ -d \"$CHANNELS_DIR\" ]; then \
        echo 'channels plugin exists, skipping install'; \
    else \
        if [ -f \"$OPENCLAW_CFG\" ]; then \
            mkdir -p /home/user/.openclaw && \
            rm -f \"$OPENCLAW_CFG_BAK\" && \
            mv \"$OPENCLAW_CFG\" \"$OPENCLAW_CFG_BAK\" && \
            echo 'Temporarily moved openclaw.json to .back302ai for plugin install'; \
        fi && \
        openclaw plugins install @openclaw-china/channels && \
        echo 'Installed openclaw channels plugin' && \
        if [ -f \"$OPENCLAW_CFG_BAK\" ]; then \
            mv -f \"$OPENCLAW_CFG_BAK\" \"$OPENCLAW_CFG\" && \
            echo 'Restored openclaw.json'; \
        fi; \
    fi && \
    mkdir -p /home/user/.claude/skills && \
    for p in /app/.skills-backup/*; do \
        name=\"$(basename \"$p\")\"; \
        cp -a \"$p\" /home/user/.claude/skills/ 2>/dev/null || true; \
        echo \"Restored skill entry (overwrite): $name\"; \
    done && \
    openclaw gateway run --port 18789 --bind lan & \
    uvicorn main:app --host 0.0.0.0 --port 8000\
"]
