import os
import logging
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
from fastmcp import FastMCP
from logging.handlers import RotatingFileHandler

# 设置默认编码为UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 读取环境变量
load_dotenv()

# 准备日志
def setup_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # 创建logs目录（如果不存在）
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 文件处理器 - 使用 RotatingFileHandler 限制文件大小
    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024*1024,  # 1MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # 设置格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 使用新的日志设置
logger = setup_logger("mcp2brave")
logger.info("Logger initialized - outputs to both console and file in logs directory")

# Create an MCP server
mcp = FastMCP("mcp2brave", dependencies=["python-dotenv", "requests"])

# 准备API密钥
API_KEY = os.getenv("BRAVE_API_KEY")
if not API_KEY:
    logger.error("BRAVE_API_KEY environment variable not found")
    raise ValueError("BRAVE_API_KEY environment variable required")

def _detect_language(text: str) -> str:
    """检测文本语言并返回对应的语言代码"""
    # 定义语言检测规则
    LANGUAGE_PATTERNS = {
        # 中文 (简体和繁体)
        'zh-hans': ('\u4e00', '\u9fff'),  # 简体中文
        'zh-hant': ('\u4e00', '\u9fff'),  # 繁体中文
        # 日文
        'jp': ('\u3040', '\u309f', '\u30a0', '\u30ff'),  # 平假名和片假名
        # 韩文
        'ko': ('\uac00', '\ud7af'),  # 谚文
        # 俄文
        'ru': ('\u0400', '\u04ff'),  # 西里尔字母
        # 阿拉伯文
        'ar': ('\u0600', '\u06ff'),
        # 希伯来文
        'he': ('\u0590', '\u05ff'),
        # 泰文
        'th': ('\u0e00', '\u0e7f'),
        # 越南文 (使用扩展拉丁字母)
        'vi': ('àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'),
        # 印地文
        'hi': ('\u0900', '\u097f'),
        # 泰米尔文
        'ta': ('\u0b80', '\u0bff'),
        # 特卢固文
        'te': ('\u0c00', '\u0c7f'),
    }

    def contains_chars_in_range(text, *ranges):
        """检查文本是否包含指定Unicode范围内的字符"""
        if len(ranges) % 2 == 0:  # 范围对
            for i in range(0, len(ranges), 2):
                start, end = ranges[i:i+2]
                if any(start <= char <= end for char in text):
                    return True
        else:  # 字符列表
            return any(char in ranges[0] for char in text)
        return False

    # 检测常见的非拉丁文字系统
    for lang, pattern in LANGUAGE_PATTERNS.items():
        if contains_chars_in_range(text, *pattern):
            # 对中文进行简繁体识别（这里使用简单规则，实际应用可能需要更复杂的逻辑）
            if lang in ['zh-hans', 'zh-hant']:
                # 这里可以添加更复杂的简繁体识别逻辑
                return 'zh-hans'  # 默认返回简体中文
            return lang

    # 检测拉丁字母语言（简单示例）
    # 注意：这是一个非常简化的实现，实际应用可能需要更复杂的语言检测
    LATIN_PATTERNS = {
        'es': ['ñ', 'á', 'é', 'í', 'ó', 'ú', '¿', '¡'],
        'fr': ['é', 'è', 'ê', 'à', 'ç', 'ù', 'û', 'ï'],
        'de': ['ä', 'ö', 'ü', 'ß'],
        'pt-pt': ['ã', 'õ', 'á', 'é', 'í', 'ó', 'ú', 'â', 'ê', 'ô'],
        'it': ['à', 'è', 'é', 'ì', 'ò', 'ó', 'ù'],
    }

    for lang, patterns in LATIN_PATTERNS.items():
        if any(pattern in text.lower() for pattern in patterns):
            return lang

    # 默认返回英语
    return "en"

def _extract_text_from_html(html_content: str) -> str:
    """从HTML内容中提取有意义的文本"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除不需要的元素
        for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'iframe', 'ad', '.advertisement']):
            element.decompose()
        
        # 优先提取文章主要内容
        article = soup.find('article')
        if article:
            content = article
        else:
            # 尝试找到主要内容区域
            content = soup.find(['main', '.content', '#content', '.post-content', '.article-content'])
            if not content:
                content = soup
        
        # 获取文本
        text = content.get_text(separator='\n')
        
        # 文本清理
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            # 跳过空行和太短的行
            if line and len(line) > 30:
                lines.append(line)
        
        # 组合文本，限制在1000字符以内
        cleaned_text = ' '.join(lines)
        if len(cleaned_text) > 1000:
            # 尝试在句子边界截断
            end_pos = cleaned_text.rfind('. ', 0, 1000)
            if end_pos > 0:
                cleaned_text = cleaned_text[:end_pos + 1]
            else:
                cleaned_text = cleaned_text[:1000]
        
        return cleaned_text
        
    except Exception as e:
        logger.error(f"Error extracting text from HTML: {str(e)}")
        # 如果无法处理HTML，返回原始内容的一部分
        text = html_content.replace('<', ' <').replace('>', '> ').split()
        return ' '.join(text)[:500]

def _do_search_with_summary(query: str) -> str:
    """Internal function to handle the search logic with summary support"""
    try:
        query = query.encode('utf-8').decode('utf-8')
        url = "https://api.search.brave.com/res/v1/web/search"
        
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": API_KEY
        }
        
        params = {
            "q": query,
            "count": 5,
            "result_filter": "web",
            "enable_summarizer": True,
            "format": "json"
        }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        logger.debug("API Response Structure:")
        logger.debug(f"Response Keys: {list(data.keys())}")
        
        # 处理搜索结果
        summary_text = ""
        search_results = []
        
        # 获取网页搜索结果
        if 'web' in data and 'results' in data['web']:
            results = data['web']['results']
            
            # 获取摘要
            if 'summarizer' in data:
                logger.debug("Found official summarizer data")
                summary = data.get('summarizer', {})
                summary_text = summary.get('text', '')
            else:
                logger.debug("No summarizer found, generating summary from top results")
                # 使用前两个结果的内容作为摘要
                try:
                    summaries = []
                    for result in results[:2]:  # 只处理前两个结果
                        url = result.get('url')
                        if url:
                            logger.debug(f"Fetching content from: {url}")
                            content = _get_url_content_direct(url)
                            # 提取HTML中的文本内容
                            raw_content = content.split('---\n\n')[-1]
                            text_content = _extract_text_from_html(raw_content)
                            if text_content:
                                # 添加标题和来源信息
                                title = result.get('title', 'No title')
                                date = result.get('age', '') or result.get('published_time', '')
                                summaries.append(f"### {title}")
                                if date:
                                    summaries.append(f"Published: {date}")
                                summaries.append(text_content)
                    
                    if summaries:
                        summary_text = "\n\n".join([
                            "Generated summary from top results:",
                            *summaries
                        ])
                        logger.debug("Successfully generated summary from content")
                    else:
                        summary_text = results[0].get('description', '')
                except Exception as e:
                    logger.error(f"Error generating summary from content: {str(e)}")
                    summary_text = results[0].get('description', '')
            
            # 处理搜索结果显示
            for result in results:
                title = result.get('title', 'No title').encode('utf-8').decode('utf-8')
                url = result.get('url', 'No URL')
                description = result.get('description', 'No description').encode('utf-8').decode('utf-8')
                search_results.append(f"- {title}\n  URL: {url}\n  Description: {description}\n")
        
        # 组合输出
        output = []
        if summary_text:
            output.append(f"Summary:\n{summary_text}\n")
        if search_results:
            output.append("Search Results:\n" + "\n".join(search_results))
        
        logger.debug(f"Has summary: {bool(summary_text)}")
        logger.debug(f"Number of results: {len(search_results)}")
        
        return "\n".join(output) if output else "No results found for your query."
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        logger.exception("Detailed error trace:")
        return f"Error performing search: {str(e)}"

def _get_url_content_direct(url: str) -> str:
    """Internal function to get content directly using requests"""
    try:
        logger.debug(f"Directly fetching content from URL: {url}")
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        response.raise_for_status()
        
        # 尝试检测编码
        if 'charset' in response.headers.get('content-type', '').lower():
            response.encoding = response.apparent_encoding
            
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除不需要的元素
            for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'iframe', 'ad', '.advertisement']):
                element.decompose()
            
            # 尝试找到主要内容区域
            main_content = None
            possible_content_elements = [
                soup.find('article'),
                soup.find('main'),
                soup.find(class_='content'),
                soup.find(id='content'),
                soup.find(class_='post-content'),
                soup.find(class_='article-content'),
                soup.find(class_='entry-content'),
                soup.find(class_='main-content'),
                soup.select_one('div[class*="content"]'),  # 包含 "content" 的任何 class
            ]
            
            for element in possible_content_elements:
                if element:
                    main_content = element
                    break
            
            if not main_content:
                main_content = soup
            
            text = main_content.get_text(separator='\n')
            
            lines = []
            for line in text.split('\n'):
                line = line.strip()
                if line and len(line) > 30:
                    lines.append(line)
            
            cleaned_text = ' '.join(lines)
            if len(cleaned_text) > 1000:
                end_pos = cleaned_text.rfind('. ', 0, 1000)
                if end_pos > 0:
                    cleaned_text = cleaned_text[:end_pos + 1]
                else:
                    cleaned_text = cleaned_text[:1000]
            
            metadata = f"URL: {url}\n"
            metadata += f"Content Length: {len(response.text)} characters\n"
            metadata += f"Content Type: {response.headers.get('content-type', 'Unknown')}\n"
            metadata += "---\n\n"
            
            return f"{metadata}{cleaned_text}"
            
        except Exception as e:
            logger.error(f"Error extracting text from HTML: {str(e)}")
            return f"Error extracting text: {str(e)}"
        
    except Exception as e:
        logger.error(f"Error fetching URL content directly: {str(e)}")
        return f"Error getting content: {str(e)}"

def _do_news_search(query: str, country: str = "all", search_lang: str = None) -> str:
    """Internal function to handle news search using Brave News API"""
    try:
        query = query.encode('utf-8').decode('utf-8')
        
        # 如果未指定语言，自动检测
        if search_lang is None:
            search_lang = _detect_language(query)
            logger.debug(f"Detected language: {search_lang} for query: {query}")
        
        url = "https://api.search.brave.com/res/v1/news/search"
        
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": API_KEY
        }
        
        params = {
            "q": query,
            "count": 10,
            "country": country,
            "search_lang": search_lang,
            "spellcheck": 1
        }
        
        logger.debug(f"Searching news for query: {query}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # 处理新闻搜索结果
        results = []
        if 'results' in data:
            for news in data['results']:
                title = news.get('title', 'No title').encode('utf-8').decode('utf-8')
                url = news.get('url', 'No URL')
                description = news.get('description', 'No description').encode('utf-8').decode('utf-8')
                date = news.get('published_time', 'Unknown date')
                source = news.get('source', {}).get('name', 'Unknown source')
                
                news_item = [
                    f"- {title}",
                    f"  Source: {source}",
                    f"  Date: {date}",
                    f"  URL: {url}",
                    f"  Description: {description}\n"
                ]
                results.append("\n".join(news_item))
        
        if not results:
            return "No news found for your query."
            
        return "News Results:\n\n" + "\n".join(results)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"News API request error: {str(e)}")
        return f"Error searching news: {str(e)}"
    except Exception as e:
        logger.error(f"News search error: {str(e)}")
        logger.exception("Detailed error trace:")
        return f"Error searching news: {str(e)}"
@mcp.tool()
def search_brave_with_summary(query: str) -> str:
    """Search the web using Brave Search API """
    return _do_search_with_summary(query)

@mcp.tool()
def brave_search_summary(query: str) -> str:
    """使用Brave搜索引擎搜索网络信息"""
    return _do_search_with_summary(query)

@mcp.tool()
def get_url_content_direct(url: str) -> str:
    """Get webpage content directly using HTTP request
    
    Args:
        url (str): The URL to fetch content from
        
    Returns:
        str: The webpage content and metadata
    """
    return _get_url_content_direct(url)

@mcp.tool()
def url_content(url: str) -> str:
    """直接获取网页内容
    
    参数:
        url (str): 目标网页地址
        
    返回:
        str: 网页内容和元数据
    """
    return _get_url_content_direct(url)

@mcp.tool()
def search_news(query: str) -> str:
    """Search news using Brave News API
    
    Args:
        query (str): The search query for news
        
    Returns:
        str: News search results including titles, sources, dates and descriptions
    """
    return _do_news_search(query)

@mcp.tool()
def search_news_info(query: str) -> str:
    """使用Brave新闻API搜索新闻
    
    参数:
        query (str): 新闻搜索关键词
        
    返回:
        str: 新闻搜索结果，包含标题、来源、日期和描述
    """
    return _do_news_search(query)