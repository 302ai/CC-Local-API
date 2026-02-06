claude_md_str = """

# Claude Code 项目规则

## 任务执行规范

### 1. TODO列表管理（强制执行）

**执行流程：**
- 创建TODO列表后，**必须逐个执行**列表中的所有任务
- 每个任务的完整流程：
  1. 标记为 `in_progress`
  2. 实际执行任务
  3. 标记为 `completed`

**严格禁止：**
- ❌ 创建TODO后只声明要做而不实际执行
- ❌ 跳过TODO直接说"任务完成"
- ❌ 在未完成所有TODO前就结束对话

### 2. 文件读取规范（强制执行）

**文件名里@表示我希望你去使用这个文件，并不是指@这个字符是文件名的一部分**

**大文件读取原则：**
- 对于超过 500 行的文件，**必须分批读取**
- 使用 `Read` 工具的 `offset` 和 `limit` 参数进行分批读取
- 每次读取建议 200-500 行，避免一次性读取造成长时间等待

**分批读取示例：**
```
第1批：Read(file_path="/path/to/file", offset=0, limit=500)
第2批：Read(file_path="/path/to/file", offset=500, limit=500)
第3批：Read(file_path="/path/to/file", offset=1000, limit=500)
...依此类推
```

**读取策略：**
- 先使用 `wc -l` 统计文件总行数
- 根据总行数判断是否需要分批
- 如果文件 ≤ 500 行，可以一次性读取
- 如果文件 > 500 行，必须分批读取

### 3. 文件内容响应规则（强制执行）

**核心原则：** 避免在响应中返回大量文件原始内容

**严格禁止：**
- ❌ 使用 `cat` 命令读取文件后将完整内容返回给用户
- ❌ 将图片转换为 Base64 并返回给用户
- ❌ 在响应中包含完整的文件数据内容
- ❌ 读取文件后直接展示全部内容

**允许的操作：**
- ✅ 使用 `ls`、`test -f`、`stat` 等命令检测文件是否存在
- ✅ 使用 `wc -l` 统计文件行数
- ✅ 使用 `file` 命令检测文件类型
- ✅ 使用 `head -n 5` 或 `tail -n 5` 查看少量内容（仅在必要时）
- ✅ 报告文件存在状态、大小、类型等元信息
- ✅ 内部读取文件进行处理，但不在响应中输出完整内容

**文件验证方式：**
```bash
# 检测文件是否存在
test -f filename && echo "文件存在" || echo "文件不存在"

# 获取文件信息
ls -la filename

# 获取文件类型
file filename
```

### 4. HTML任务特殊要求

**适用范围：** 仅适用于生成HTML代码的任务

**最高优先级规则：**
- 主HTML文件**必须**命名为 `index.html`
- 必须保存在**工作目录根路径**下
- 如果代码会引用非工作目录的本地文件，**必须**先拷贝到工作目录，生成的代码默认使用工作目录下的文件路径

**执行步骤：**
1. 使用 `Write` 工具保存 `index.html`
2. 等待保存确认
3. 使用 `ls -la index.html` 验证文件存在（不要 cat 文件内容）

### 5. 代码保存要求（所有代码任务）

**保存标准：**
- 所有生成的代码**必须**成功保存到本地文件
- 必须使用 `Write` 工具保存文件
- 必须等待保存成功的确认消息

**任务完成判定：**
- ✅ 只有收到文件保存成功确认，任务才算完成
- ❌ 只展示代码而不保存文件，**不算**任务完成

### 6. 任务完成输出（强制执行）

在所有任务成功完成后，**必须**执行以下步骤：

**第1步：输出工作目录信息**
```bash
pwd
```

**第2步：列出文件清单**
```bash
ls -la
```

**第3步：明确输出以下信息**
- 当前工作目录的绝对路径
- 本次任务**新增**的文件完整路径列表
- 本次任务**修改**的文件完整路径列表

**输出格式示例：**
```
## 任务完成报告

**工作目录：** /home/user/workspace/xxxx

**新增文件：**
- /home/user/workspace/xxxx/index.html
- /home/user/workspace/xxxx/style.css
- /home/user/workspace/xxxx/script.js

**修改文件：**
- 无
```


### 8. 任务完成检查清单

在说"任务完成"之前，**必须**确认以下所有项：

- [ ] TODO列表中的所有任务都已标记为 `completed`
- [ ] 所有代码文件都已成功保存（已收到保存确认）
- [ ] （如为HTML任务）`index.html` 已保存在工作目录根路径
- [ ] 已执行 `pwd` 和 `ls -la` 命令
- [ ] 已输出工作目录信息和文件路径列表
- [ ] 已使用 `ls` 命令验证文件确实存在（不是 cat 内容）
- [ ] 响应中没有包含完整的文件内容或 Base64 数据

**只有完成以上所有检查项，才能说"任务完成"。**

---

## 沙盒环境配置说明

### Python 环境

**Python 版本：**
- 系统使用 Python 3
- 执行 Python 脚本时必须使用 `python3` 命令（不是 `python`）

**已安装的第三方库(禁止卸载或更新这四个库)：**
- `requests` - HTTP 请求库
- `playwright` - 浏览器自动化（Python 版）
- `beautifulsoup4` - HTML 解析库
- `matplotlib` - 数据可视化库


**查看已安装库：**
```bash
python3 -m pip list
```

**安装新库（如需要）：**
```bash
python3 -m pip install --no-cache-dir --break-system-packages <package-name>
```

### Playwright 使用说明

#### Python 版 Playwright

1. **浏览器支持：**
- 已安装 Chromium 浏览器及其依赖

2. **环境变量要求：**
   - 必须设置 `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`

**使用示例：**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com")
    # ... 你的代码
    browser.close()
```

#### Node.js 版 Playwright

**关键配置要求（必须遵守）：**

1. **工作目录要求：**
   - 所有 Playwright 脚本必须在 `/app` 目录下运行
   - 浏览器二进制文件安装在 `/app` 目录
   - 执行前必须先 `cd /app`

2. **环境变量要求：**
   - 必须设置 `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`


**正确的执行方式：**
```bash
cd /app
PLAYWRIGHT_BROWSERS_PATH=/ms-playwright node your-script.js
```

或在脚本中：
```bash
cd /app
PLAYWRIGHT_BROWSERS_PATH=/ms-playwright npx playwright test
```

**Node.js Playwright 使用示例：**
```javascript
// 文件位置：/app/script.js
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('https://example.com');
  // ... 你的代码
  await browser.close();
})();
```
---

"""