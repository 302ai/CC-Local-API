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
  && npm install -g openclaw@2026.3.23-2 \
  && npm install -g clawhub@latest \
  && npm install -g @playwright/cli@latest \
  && npm install -g acpx@latest \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && rm -rf /root/.npm \
  && rm -rf /tmp/*

# 创建目录并设置权限
RUN mkdir -p /data /app /home/user/.claude/skills /home/user/.openclaw /home/user/db && \
  chmod 755 /home/user/.openclaw /home/user/.claude /home/user/.claude/skills && \
  chmod 755 /data /app /home/user

# 预下载 acpx skill 和文档
RUN curl -fsSL -o /home/user/.claude/skills/SKILL.md \
  https://raw.githubusercontent.com/openclaw/acpx/main/skills/acpx/SKILL.md && \
  mkdir -p /home/user/acpx/docs && \
  curl -fsSL -o /home/user/acpx/docs/CLI.md \
  https://raw.githubusercontent.com/openclaw/acpx/main/docs/CLI.md

# 安装 Python 依赖
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . /app

# 复制自定义 skills 到不会被挂载覆盖的目录
COPY skills/ /app/.skills-backup/

ENV HOME=/home/user

# 安装插件
RUN openclaw plugins install @openclaw-china/channels@latest
RUN openclaw plugins install @openclaw/acpx
RUN #npx -y @tencent-weixin/openclaw-weixin-cli@latest install

# 把插件数据备份到不会被挂载覆盖的目录
RUN mkdir -p /app/.openclaw-extensions-backup && \
  cp -a /home/user/.openclaw/extensions /app/.openclaw-extensions-backup/

# 复制启动脚本
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000 18789

CMD ["/app/entrypoint.sh"]
