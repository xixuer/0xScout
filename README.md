# 0xScout - 技术情报收集与分析工具

0xScout是一个用于收集和分析技术情报的工具，可以从GitHub和HackerNews等平台获取信息，并生成摘要报告。

## 项目结构

```
0xScout/
├── config.json              # 配置文件
├── main.py                  # 主入口文件
├── requirements.txt         # 依赖包列表
├── src/                     # 源代码目录
│   ├── core/                # 核心组件
│   │   └── base_report_generator.py  # 报告生成器基类
│   ├── clients/             # 客户端模块
│   │   ├── github_client.py         # GitHub客户端
│   │   └── hacker_news_client.py    # HackerNews客户端
│   ├── generators/          # 报告生成器
│   │   ├── github_report_generator.py       # GitHub报告生成器
│   │   ├── hacker_news_report_generator.py  # HackerNews报告生成器
│   │   └── report_generator_factory.py      # 报告生成器工厂
│   ├── utils/               # 工具模块
│   │   └── cache_manager.py          # 缓存管理器
│   └── examples/            # 示例代码
│       └── example.py               # 使用示例
└── cache/                   # 缓存目录
    ├── github/              # GitHub API缓存
    └── hackernews/          # HackerNews API缓存
```

## 功能特性

- **GitHub情报收集**：
  - 获取仓库的提交、问题和拉取请求
  - 获取仓库的最新发布版本
  - 生成仓库活动摘要报告

- **HackerNews情报收集**：
  - 获取热门文章列表
  - 获取文章评论
  - 生成热门文章摘要报告
  - 生成文章评论摘要报告

- **性能优化**：
  - 异步HTTP请求
  - API响应缓存
  - 批量并行处理

- **架构优化**：
  - 基于接口的设计
  - 工厂模式创建报告生成器
  - 依赖注入降低耦合

## 安装

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/0xScout.git
cd 0xScout
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 创建配置文件：

创建`config.json`文件，内容如下：

```json
{
  "github_token": "your_github_token",
  "use_cache": true,
  "cache_ttl": 3600
}
```

## 使用方法

### 命令行使用

#### 生成GitHub报告

```bash
# 生成单个仓库报告
python main.py github --repo microsoft/vscode --days 7

# 使用异步模式
python main.py github --repo microsoft/vscode --days 7 --async

# 批量生成多个仓库报告
python main.py github --batch --repos microsoft/vscode,facebook/react,tensorflow/tensorflow --days 7
```

#### 生成HackerNews报告

```bash
# 生成热门文章报告
python main.py hackernews --limit 20

# 生成文章评论报告
python main.py hackernews --story-id 34231234 --limit 30

# 使用异步模式
python main.py hackernews --async
```

#### 运行示例代码

```bash
python main.py example
```

### 在代码中使用

```python
from src.generators.report_generator_factory import ReportGeneratorFactory

# 创建LLM实例（这里使用模拟实现）
class MockLLM:
    def generate_text(self, prompt):
        return f"生成的文本: {prompt[:30]}..."

# 配置
config = {
    "github_token": "your_github_token",
    "use_cache": True,
    "cache_ttl": 3600
}

# 创建报告生成器
llm = MockLLM()
github_generator = ReportGeneratorFactory.create_generator("github", llm, config)

# 生成报告
report = github_generator.generate_report(repo="microsoft/vscode", days=7)
print(report)
```

## 异步使用

```python
import asyncio
from src.generators.report_generator_factory import ReportGeneratorFactory

# 创建LLM实例
class MockLLM:
    async def async_generate_text(self, prompt):
        return f"异步生成的文本: {prompt[:30]}..."

async def main():
    # 配置
    config = {
        "github_token": "your_github_token",
        "use_cache": True,
        "cache_ttl": 3600
    }
    
    # 创建报告生成器
    llm = MockLLM()
    github_generator = ReportGeneratorFactory.create_generator("github", llm, config)
    
    # 异步生成报告
    report = await github_generator.async_generate_repo_summary("microsoft/vscode", days=7)
    print(report)

# 运行异步函数
asyncio.run(main())
```

## 环境变量

- `GITHUB_TOKEN`: GitHub API令牌（如果未在配置文件中指定）

## 依赖

- Python 3.7+
- aiohttp
- requests
- beautifulsoup4

