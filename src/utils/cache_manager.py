import json
import os
import time
from typing import Any, Dict, Optional

try:
    from src.logger import LOG
except ImportError:
    import logging
    LOG = logging.getLogger(__name__)

class CacheManager:
    """
    缓存管理器，用于缓存API响应，减少对外部API的请求次数
    """
    def __init__(self, cache_dir: str = "cache", default_ttl: int = 3600):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录
            default_ttl: 默认缓存有效期（秒）
        """
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> str:
        """获取缓存文件路径"""
        # 将key转换为文件安全的名称
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            key: 缓存键名
            
        Returns:
            缓存的数据，如果缓存不存在或已过期则返回None
        """
        cache_path = self._get_cache_path(key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 检查缓存是否过期
            if time.time() > cache_data.get('expires_at', 0):
                LOG.debug(f"缓存已过期: {key}")
                return None
            
            LOG.debug(f"命中缓存: {key}")
            return cache_data.get('data')
        except Exception as e:
            LOG.error(f"读取缓存失败: {key}, 错误: {e}")
            return None
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存数据
        
        Args:
            key: 缓存键名
            data: 要缓存的数据
            ttl: 缓存有效期（秒），如果为None则使用默认值
            
        Returns:
            是否成功设置缓存
        """
        if ttl is None:
            ttl = self.default_ttl
        
        cache_path = self._get_cache_path(key)
        
        try:
            cache_data = {
                'data': data,
                'created_at': time.time(),
                'expires_at': time.time() + ttl
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            LOG.debug(f"设置缓存: {key}, TTL: {ttl}秒")
            return True
        except Exception as e:
            LOG.error(f"设置缓存失败: {key}, 错误: {e}")
            return False
    
    def invalidate(self, key: str) -> bool:
        """
        使缓存失效
        
        Args:
            key: 缓存键名
            
        Returns:
            是否成功使缓存失效
        """
        cache_path = self._get_cache_path(key)
        
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                LOG.debug(f"已使缓存失效: {key}")
                return True
            except Exception as e:
                LOG.error(f"使缓存失效失败: {key}, 错误: {e}")
        
        return False
    
    def clear_all(self) -> int:
        """
        清除所有缓存
        
        Returns:
            清除的缓存数量
        """
        count = 0
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                try:
                    os.remove(os.path.join(self.cache_dir, filename))
                    count += 1
                except Exception as e:
                    LOG.error(f"清除缓存失败: {filename}, 错误: {e}")
        
        LOG.info(f"已清除 {count} 个缓存文件")
        return count 