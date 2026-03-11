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
    && npm install -g @anthropic-ai/claude-code \
    && npm install -g openclaw@latest \
    && npm install -g clawhub@latest \
    && npm install -g @playwright/cli@latest \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.npm \
    && rm -rf /tmp/*

# 创建用户
RUN groupadd -r user && useradd -r -g user -m -s /bin/bash user

# 创建目录并设置权限（755 而非 775，避免 world-writable 问题）
RUN mkdir -p /data /data/user /app /home/user/.claude /home/user/.openclaw /home/user/db && \
    chown -R user:user /data /app /home/user && \
    chmod 755 /data /app /home/user && \
    chmod 755 /home/user/db /home/user/.claude /home/user/.openclaw

# 安装 Python 依赖
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
USER user
COPY --chown=user:user . /app

ENV HOME=/home/user

# 安装插件
RUN openclaw plugins install @openclaw-china/channels

# 把插件数据备份到不会被挂载覆盖的目录，并确保备份权限安全
RUN mkdir -p /app/.openclaw-extensions-backup && \
    cp -a /home/user/.openclaw/extensions /app/.openclaw-extensions-backup/ && \
    chmod -R go-w /app/.openclaw-extensions-backup/

EXPOSE 8000 18789

# 启动时检查 channels 插件是否存在，不存在才恢复；恢复后修正权限
CMD ["sh", "-c", "\
    if [ ! -d \"/home/user/.openclaw/extensions/channels\" ]; then \
        mkdir -p /home/user/.openclaw/extensions && \
        cp -a /app/.openclaw-extensions-backup/extensions/* /home/user/.openclaw/extensions/ 2>/dev/null || true; \
        echo 'Restored openclaw extensions (channels plugin was missing)'; \
    else \
        echo 'channels plugin exists, skipping restore'; \
    fi && \
    chmod -R go-w /home/user/.openclaw/extensions && \
    find /home/user/.openclaw/extensions -type d -exec chmod 755 {} + && \
    find /home/user/.openclaw/extensions -type f -exec chmod 644 {} + && \
    echo 'Extensions permissions fixed (755/644)' && \
    openclaw gateway run --port 18789 --bind lan & \
    uvicorn main:app --host 0.0.0.0 --port 8000 \
"]
