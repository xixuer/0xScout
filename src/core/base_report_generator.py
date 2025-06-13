from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Generator, Union

class BaseReportGenerator(ABC):
    """
    报告生成器的基础接口类
    定义了所有报告生成器需要实现的方法
    """
    
    @abstractmethod
    def __init__(self, llm, settings):
        """
        初始化报告生成器
        
        Args:
            llm: 语言模型实例
            settings: 配置设置实例
        """
        pass
    
    @abstractmethod
    def _preload_prompts(self):
        """
        预加载提示模板
        """
        pass
    
    @abstractmethod
    def generate_report(self, *args, **kwargs) -> Union[str, Generator[str, None, None]]:
        """
        生成报告
        
        Returns:
            生成的报告内容，可以是字符串或生成器
        """
        pass 