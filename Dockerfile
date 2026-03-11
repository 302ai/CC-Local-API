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

# 创建目录并设置权限
RUN mkdir -p /data /data/user /app /home/user/.claude /home/user/.openclaw /home/user/db && \
    chown -R user:user /data /app /home/user && \
    chmod 755 /data /app /home/user && \
    chmod 775 /home/user/db /home/user/.claude /home/user/.openclaw

# 安装 Python 依赖
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
USER user
COPY --chown=user:user . /app

ENV HOME=/home/user

RUN openclaw plugins install @openclaw-china/channels

EXPOSE 8000 18789
CMD ["sh", "-c", "openclaw gateway run --port 18789 --bind lan & uvicorn main:app --host 0.0.0.0 --port 8000"]
