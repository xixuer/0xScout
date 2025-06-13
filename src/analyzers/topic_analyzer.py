"""
Hacker News 话题分析模块
用于分析和聚类 Hacker News 文章，识别热门话题和趋势
"""

import os
import re
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional, Tuple, Set

# NLP相关库
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer, WordNetLemmatizer
from nltk.util import ngrams

# 机器学习相关库
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import TruncatedSVD, LatentDirichletAllocation
from sklearn.metrics.pairwise import cosine_similarity

# 导入日志
try:
    from src.logger import LOG
except ImportError:
    import logging
    LOG = logging.getLogger(__name__)

# 确保NLTK数据已下载
def ensure_nltk_data():
    """确保NLTK必要的数据包已下载"""
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        LOG.info("下载NLTK punkt数据包...")
        nltk.download('punkt', quiet=True)
    
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        LOG.info("下载NLTK stopwords数据包...")
        nltk.download('stopwords', quiet=True)
    
    try:
        nltk.data.find('corpora/wordnet')
    except LookupError:
        LOG.info("下载NLTK wordnet数据包...")
        nltk.download('wordnet', quiet=True)
        
    # 添加punkt_tab下载
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        LOG.info("下载NLTK punkt_tab数据包...")
        try:
            nltk.download('punkt', quiet=True)  # punkt包含punkt_tab所需的数据
        except Exception as e:
            LOG.warning(f"无法下载punkt_tab数据包: {e}")
            # 修改使用替代方法
            import nltk.tokenize as nt
            # 确保punkt_tokenize可用作为替代方案
            nltk.tokenize.sent_tokenize = lambda text, language='english': text.split('.')
            LOG.info("已使用替代分句方法替换punkt_tab功能")


class HackerNewsTopicAnalyzer:
    """Hacker News 话题分析器"""
    
    def __init__(self, cache_dir='cache/topic_analysis'):
        """
        初始化话题分析器
        
        Args:
            cache_dir: 缓存目录，用于存储历史话题数据
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # 初始化NLP组件
        ensure_nltk_data()
        self.stop_words = set(stopwords.words('english'))
        self.tech_stop_words = {'use', 'using', 'used', 'new', 'data', 'create', 'like', 
                               'simple', 'build', 'building', 'built', 'tech', 'technology'}
        self.stop_words.update(self.tech_stop_words)
        
        # 添加一些技术术语和公司名称到词库
        self.tech_entities = {
            'javascript', 'python', 'java', 'cpp', 'c++', 'rust', 'golang', 'go', 
            'typescript', 'react', 'angular', 'vue', 'node', 'nodejs', 'django', 'flask',
            'ai', 'ml', 'deeplearning', 'machinelearning', 'llm', 'gpt', 'openai', 'github',
            'aws', 'azure', 'google', 'microsoft', 'apple', 'facebook', 'meta', 'amazon',
            'blockchain', 'crypto', 'bitcoin', 'ethereum', 'nft', 'web3',
            'frontend', 'backend', 'fullstack', 'devops', 'database', 'api'
        }
        
        self.stemmer = PorterStemmer()
        self.lemmatizer = WordNetLemmatizer()
        
        # 向量化器
        self.vectorizer = TfidfVectorizer(
            max_features=1000,  # 限制特征数量，适应内存限制
            min_df=2,           # 至少在2篇文章中出现
            max_df=0.8,         # 在不超过80%的文章中出现
            ngram_range=(1, 2)  # 同时考虑单词和双词组合
        )
        
        # 历史话题数据
        self.historical_topics = {}
    
    def preprocess_text(self, text):
        """
        文本预处理
        
        Args:
            text: 原始文本字符串
            
        Returns:
            预处理后的字符串
        """
        if not text:
            return ""
            
        # 转为小写
        text = text.lower()
        
        # 移除URL
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', ' ', text)
        
        # 移除特殊字符和数字
        text = re.sub(r'[^a-zA-Z\s]', ' ', text)
        
        # 标记化 - 避免使用word_tokenize（依赖于punkt_tab）
        try:
            # 尝试使用word_tokenize
            tokens = word_tokenize(text)
        except LookupError:
            # 回退到简单的空格分割
            LOG.warning("无法使用NLTK word_tokenize，回退到基本分词")
            tokens = text.split()
        
        # 过滤停用词
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 2]
        
        # 词形还原 (更轻量级，比词干提取更符合语义)
        tokens = [self.lemmatizer.lemmatize(t) for t in tokens]
        
        # 识别技术实体 (保留完整形式)
        for i, token in enumerate(tokens):
            if token in self.tech_entities:
                tokens[i] = f"TECH_{token.upper()}"
        
        return ' '.join(tokens)
    
    def preprocess_stories(self, stories):
        """
        预处理HackerNews故事
        
        Args:
            stories: HN故事列表
            
        Returns:
            预处理后的文本和元数据
        """
        processed_texts = []
        metadata = []
        
        for story in stories:
            # 提取相关字段
            story_id = story.get('id')
            title = story.get('title', '')
            url = story.get('url', '')
            text = story.get('text', '')  # Ask HN等帖子的文本内容
            
            # 解析URL的域名作为额外信息
            domain = ''
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                except:
                    pass
            
            # 组合标题和文本
            combined_text = f"{title} {text} {domain}"
            
            # 预处理
            processed_text = self.preprocess_text(combined_text)
            
            processed_texts.append(processed_text)
            metadata.append({
                'id': story_id,
                'title': title,
                'url': url,
                'score': story.get('score', 0),
                'by': story.get('by', ''),
                'time': story.get('time', 0),
                'descendants': story.get('descendants', 0)  # 评论数
            })
        
        return processed_texts, metadata
    
    def cluster_topics(self, processed_texts, metadata, n_clusters=None):
        """
        聚类话题
        
        Args:
            processed_texts: 预处理后的文本列表
            metadata: 故事元数据
            n_clusters: 聚类数量，如果为None则自动确定
            
        Returns:
            聚类结果
        """
        if not processed_texts:
            return [], []
        
        # 向量化
        try:
            X = self.vectorizer.fit_transform(processed_texts)
        except ValueError:
            # 如果文本都是空的，返回空结果
            LOG.warning("无法向量化文本，可能全是停用词")
            return [0] * len(processed_texts), []
        
        # 如果数据太少，所有故事归为一个话题
        if len(processed_texts) < 3:
            LOG.info("故事数量太少，全部归为一个话题")
            return [0] * len(processed_texts), [self.extract_topic_keywords(X, [0] * len(processed_texts), 0)]
        
        # 降维以加速聚类 (适合资源受限环境)
        if X.shape[1] > 100:
            svd = TruncatedSVD(n_components=min(50, X.shape[0] - 1))
            X_reduced = svd.fit_transform(X)
        else:
            X_reduced = X.toarray()
        
        # 判断使用的聚类算法
        if n_clusters is None:
            # 使用DBSCAN自动确定聚类数
            clustering = DBSCAN(eps=0.5, min_samples=2)
            labels = clustering.fit_predict(X_reduced)
            
            # 如果大部分为噪声点 (-1)，尝试调整参数
            if (labels == -1).sum() > len(labels) * 0.5:
                LOG.debug("DBSCAN聚类产生过多噪声点，尝试K-Means")
                # 使用K-Means，聚类数量估计为文章数的1/3，最少3个，最多7个
                k = max(3, min(7, len(processed_texts) // 3))
                clustering = KMeans(n_clusters=k, random_state=42)
                labels = clustering.fit_predict(X_reduced)
        else:
            # 指定聚类数量
            clustering = KMeans(n_clusters=n_clusters, random_state=42)
            labels = clustering.fit_predict(X_reduced)
        
        # 提取每个聚类的关键词
        topics = []
        unique_labels = sorted(set(labels))
        for label in unique_labels:
            if label == -1:  # 跳过噪声点
                continue
            topics.append(self.extract_topic_keywords(X, labels, label))
        
        return labels, topics
    
    def extract_topic_keywords(self, X, labels, label_id, top_n=5):
        """
        提取聚类的关键词
        
        Args:
            X: TF-IDF矩阵
            labels: 聚类标签
            label_id: 当前聚类的ID
            top_n: 返回的关键词数量
            
        Returns:
            话题关键词和权重
        """
        if hasattr(X, 'toarray'):
            X = X.toarray()
        
        # 获取该聚类的所有文档
        cluster_docs = np.where(np.array(labels) == label_id)[0]
        
        if len(cluster_docs) == 0:
            return {'keywords': []}
        
        # 获取该聚类的TF-IDF均值
        centroid = X[cluster_docs].mean(axis=0)
        
        # 获取特征名称
        if hasattr(self.vectorizer, 'get_feature_names_out'):
            feature_names = self.vectorizer.get_feature_names_out()
        else:
            feature_names = self.vectorizer.get_feature_names()
        
        # 排序并获取top关键词
        indices = centroid.argsort()[-top_n:][::-1]
        keywords = [(feature_names[i], float(centroid[i])) for i in indices]
        
        return {
            'id': label_id,
            'keywords': keywords,
            'size': len(cluster_docs)
        }
    
    def analyze_topics(self, stories, date=None, hour=None):
        """
        分析故事话题
        
        Args:
            stories: HN故事列表
            date: 日期字符串 (YYYY-MM-DD)
            hour: 小时字符串 (HH)
            
        Returns:
            话题分析结果
        """
        if not stories:
            return {
                'topics': [],
                'stories_by_topic': {},
                'trends': {
                    'emerging': [],
                    'continuing': [],
                    'fading': []
                }
            }
        
        # 确定时间
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        if hour is None:
            hour = datetime.now().strftime('%H')
            
        LOG.info(f"分析 {date} {hour}:00 的Hacker News话题")
        
        # 预处理文本
        processed_texts, metadata = self.preprocess_stories(stories)
        
        # 聚类
        labels, topics = self.cluster_topics(processed_texts, metadata)
        
        # 将故事按话题分组
        stories_by_topic = defaultdict(list)
        for i, label in enumerate(labels):
            if label != -1:  # 忽略噪声点
                topic_idx = list(set(labels)).index(label) if label in set(labels) else -1
                if topic_idx >= 0 and topic_idx < len(topics):
                    stories_by_topic[topic_idx].append(metadata[i])
        
        # 加载历史话题用于趋势分析
        prev_hour_key = self._get_previous_hour_key(date, hour)
        historical_topics = self._load_historical_topics(prev_hour_key)
        
        # 趋势分析
        trends = self._analyze_trends(topics, historical_topics)
        
        # 保存当前话题
        current_key = f"{date}_{hour}"
        self._save_topics(current_key, topics)
        
        return {
            'topics': topics,
            'stories_by_topic': dict(stories_by_topic),
            'trends': trends,
            'date': date,
            'hour': hour
        }
    
    def _get_previous_hour_key(self, date, hour):
        """获取前一小时的键"""
        dt = datetime.strptime(f"{date} {hour}:00:00", "%Y-%m-%d %H:%M:%S")
        prev_dt = dt - timedelta(hours=1)
        return f"{prev_dt.strftime('%Y-%m-%d')}_{prev_dt.strftime('%H')}"
    
    def _load_historical_topics(self, key):
        """加载历史话题数据"""
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except:
                LOG.warning(f"无法加载历史话题数据：{file_path}")
        return []
    
    def _save_topics(self, key, topics):
        """保存当前话题数据"""
        file_path = os.path.join(self.cache_dir, f"{key}.json") 
        try:
            with open(file_path, 'w') as f:
                json.dump(topics, f)
        except:
            LOG.warning(f"无法保存话题数据：{file_path}")
    
    def _analyze_trends(self, current_topics, historical_topics):
        """分析话题趋势"""
        if not historical_topics or not current_topics:
            # 没有历史数据或当前话题为空，所有话题都是新兴的
            return {
                'emerging': list(range(len(current_topics))),
                'continuing': [],
                'fading': []
            }
        
        # 计算话题相似度
        similarity_matrix = self._compute_topic_similarity(current_topics, historical_topics)
        
        # 识别趋势
        emerging = []
        continuing = []
        fading_hist_indices = list(range(len(historical_topics)))
        
        threshold = 0.3  # 话题相似度阈值
        
        # 对每个当前话题
        for i, topic in enumerate(current_topics):
            max_sim = 0
            max_idx = -1
            
            # 查找最相似的历史话题
            for j, hist_topic in enumerate(historical_topics):
                if similarity_matrix[i][j] > max_sim:
                    max_sim = similarity_matrix[i][j]
                    max_idx = j
            
            if max_sim >= threshold:
                # 话题持续
                continuing.append({
                    'current_idx': i,
                    'historical_idx': max_idx,
                    'similarity': max_sim
                })
                if max_idx in fading_hist_indices:
                    fading_hist_indices.remove(max_idx)
            else:
                # 新话题
                emerging.append(i)
        
        return {
            'emerging': emerging,
            'continuing': continuing,
            'fading': fading_hist_indices
        }
    
    def _compute_topic_similarity(self, topics1, topics2):
        """计算两组话题间的相似度"""
        similarity_matrix = []
        
        for topic1 in topics1:
            row = []
            keywords1 = dict(topic1.get('keywords', []))
            
            for topic2 in topics2:
                keywords2 = dict(topic2.get('keywords', []))
                
                # 计算共同关键词的相似度
                common_keywords = set(keywords1.keys()) & set(keywords2.keys())
                if not common_keywords:
                    row.append(0)
                    continue
                
                # 计算共同关键词的权重相似度
                similarity = 0
                for keyword in common_keywords:
                    similarity += min(keywords1.get(keyword, 0), keywords2.get(keyword, 0))
                
                # 归一化
                norm1 = sum(keywords1.values())
                norm2 = sum(keywords2.values())
                if norm1 and norm2:
                    similarity /= (norm1 * norm2) ** 0.5
                
                row.append(similarity)
            
            similarity_matrix.append(row)
        
        return similarity_matrix
    
    def generate_report(self, analysis_result):
        """
        根据分析结果生成报告
        
        Args:
            analysis_result: 话题分析结果
            
        Returns:
            Markdown格式的报告
        """
        if not analysis_result or not analysis_result.get('topics'):
            return "未发现任何话题。"
        
        topics = analysis_result['topics']
        stories_by_topic = analysis_result.get('stories_by_topic', {})
        trends = analysis_result.get('trends', {})
        date = analysis_result.get('date', datetime.now().strftime('%Y-%m-%d'))
        hour = analysis_result.get('hour', datetime.now().strftime('%H'))
        
        # 报告头部
        report = [f"# Hacker News 话题分析 ({date} {hour}:00)\n"]
        
        # 总结部分
        report.append(f"## 总体概况\n")
        report.append(f"本小时共发现 **{len(topics)}** 个主要话题。\n")
        
        if trends['emerging']:
            report.append(f"- 新兴话题: **{len(trends['emerging'])}** 个\n")
        if trends['continuing']:
            report.append(f"- 持续话题: **{len(trends['continuing'])}** 个\n")
        
        # 每个话题详情
        report.append(f"\n## 话题详情\n")
        
        # 首先处理新兴话题
        if trends['emerging']:
            report.append(f"### 新兴话题\n")
            for topic_idx in trends['emerging']:
                if topic_idx < len(topics):
                    topic = topics[topic_idx]
                    report.append(self._format_topic_section(topic, stories_by_topic.get(topic_idx, []), is_new=True))
        
        # 然后处理持续话题
        if trends['continuing']:
            report.append(f"### 持续热门话题\n")
            for cont in trends['continuing']:
                topic_idx = cont['current_idx']
                if topic_idx < len(topics):
                    topic = topics[topic_idx]
                    report.append(self._format_topic_section(topic, stories_by_topic.get(topic_idx, []), is_continuing=True))
        
        return '\n'.join(report)
    
    def _format_topic_section(self, topic, stories, is_new=False, is_continuing=False):
        """格式化单个话题的报告部分"""
        # 获取关键词
        keywords = topic.get('keywords', [])
        keyword_text = ', '.join([kw for kw, _ in keywords]) if keywords else "无关键词"
        
        topic_title = "🔥 " if is_new else "📌 " if is_continuing else ""
        topic_title += f"**{keyword_text}**"
        
        section = [f"#### {topic_title}\n"]
        
        # 添加故事列表
        if stories:
            # 按分数排序
            sorted_stories = sorted(stories, key=lambda x: x.get('score', 0), reverse=True)
            
            for i, story in enumerate(sorted_stories[:5]):  # 最多显示5个
                title = story.get('title', '无标题')
                url = story.get('url', '')
                score = story.get('score', 0)
                
                if not url:
                    url = f"https://news.ycombinator.com/item?id={story.get('id', '')}"
                
                section.append(f"- [{title}]({url}) ({score} 分)")
            
            # 如果有更多故事
            if len(sorted_stories) > 5:
                section.append(f"- *...还有 {len(sorted_stories) - 5} 个相关故事*")
        else:
            section.append("*没有相关故事*")
        
        section.append("\n")
        return '\n'.join(section)

# 单元测试和示例用例
if __name__ == "__main__":
    from src.clients.hacker_news_client import HackerNewsClient
    
    analyzer = HackerNewsTopicAnalyzer()
    client = HackerNewsClient()
    
    # 获取当前热门故事
    stories = client.get_top_stories_details(limit=30)
    
    if stories:
        # 分析话题
        result = analyzer.analyze_topics(stories)
        
        # 生成报告
        report = analyzer.generate_report(result)
        print(report)
        
        # 保存报告
        date = datetime.now().strftime('%Y-%m-%d')
        hour = datetime.now().strftime('%H')
        os.makedirs(f"hacker_news/{date}", exist_ok=True)
        with open(f"hacker_news/{date}/{hour}_topics.md", 'w') as f:
            f.write(report)
    else:
        print("无法获取Hacker News故事")

# 将限制降至更小的值
max_content_length = 5000  # 更激进的截断 