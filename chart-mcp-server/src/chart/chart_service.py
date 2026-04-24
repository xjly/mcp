"""图表服务 - 图表数据处理和生成"""

import json
import re
from typing import Any, Dict, List, Optional
import os

default_bucket = os.getenv("DEFAULT_BUCKET", "kb-images")
default_chat_path = os.getenv("DEFAULT_CHAT_IMAGES_PATH", "chat-images")

class ChartService:
    """图表处理服务"""
    
    def infer_chart_type(self, data: List[Dict], preferred: Optional[str] = None, text: str = "") -> str:
        """智能推断图表类型"""
        if preferred:
            return preferred
        
        water_keywords = ["水位", "流量", "压力", "降雨", "level", "flow", "trend"]
        is_water_data = any(k in text for k in water_keywords)
        
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, (int, float)):
                return "histogram"
            
            if isinstance(first, dict):
                if is_water_data:
                    return "area"
                if len(data) <= 7:
                    return "pie"
        
        return "bar"
    
    def build_chart_spec(
        self, 
        chart_type: str, 
        title: str, 
        data: List[Dict], 
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """构建图表规格"""
        if not data:
            raise ValueError("数据不能为空")
        
        # 处理数据格式
        values = data
        sample = values[0] if values else {}
        fields = list(sample.keys()) if isinstance(sample, dict) else []
        
        x_field = next((k for k in ("time", "date", "name", "category", "label", "x") if k in fields), None)
        y_field = next((k for k in ("level", "value", "amount", "count", "y") if k in fields), None)
        
        if not x_field and len(fields) > 0:
            x_field = fields[0]
        if not y_field and len(fields) > 1:
            y_field = fields[1]
        
        x_field = x_field or "x"
        y_field = y_field or "y"
        
        return {
            "type": chart_type,
            "title": title or "监测态势图",
            "x_field": x_field,
            "y_field": y_field,
            "values": values,
            "threshold": threshold or sample.get("threshold")
        }
    
    def parse_data_json(self, data_json: Any) -> List[Dict]:
        """智能解析数据 JSON（完整版）"""
        # 如果已经是列表
        if isinstance(data_json, list):
            return data_json
        
        # 如果是字典
        if isinstance(data_json, dict):
            if "values" in data_json:
                return data_json["values"]
            return [{"name": k, "value": v} for k, v in data_json.items()]
        
        # 如果是字符串，尝试解析
        if isinstance(data_json, str):
            clean_str = data_json.strip().strip("'").strip('"')
            
            # 尝试直接解析
            try:
                result = json.loads(clean_str)
                if isinstance(result, list):
                    return result
                if isinstance(result, dict):
                    if "values" in result:
                        return result["values"]
                    return [{"name": k, "value": v} for k, v in result.items()]
            except json.JSONDecodeError:
                pass
            
            # 修复单引号问题
            try:
                fixed_str = clean_str.replace("'", '"')
                result = json.loads(fixed_str)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
            
            # 修复属性名缺少引号的问题
            try:
                fixed_str = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', clean_str)
                result = json.loads(fixed_str)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
            
            # 从文本中提取数字
            numbers = re.findall(r'(\d+(?:\.\d+)?)', clean_str)
            if numbers:
                return [{"name": f"值{i+1}", "value": float(n)} for i, n in enumerate(numbers)]
        
        raise ValueError(f"无法解析的数据格式: {data_json}")
    
    def normalize_data(self, data: List[Dict]) -> List[Dict]:
        """标准化数据格式（完整版）"""
        normalized = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                name = None
                value = None
                
                for key in ["name", "label", "category", "x", "季度", "月份", "时期"]:
                    if key in item:
                        name = item[key]
                        break
                
                for key in ["value", "amount", "count", "y", "数值", "数量"]:
                    if key in item:
                        value = item[key]
                        break
                
                if name is None:
                    name = f"项{i+1}"
                if value is None:
                    for v in item.values():
                        if isinstance(v, (int, float)):
                            value = v
                            break
                    if value is None:
                        value = 0
                
                normalized.append({"name": str(name), "value": float(value)})
            elif isinstance(item, (int, float)):
                normalized.append({"name": f"项{i+1}", "value": float(item)})
        
        return normalized
    
    def is_fake_uuid_url(self, url: str) -> bool:
        """检测是否是伪造的 UUID URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.lstrip("/").split("/") if p]
            
            if len(path_parts) == 1:
                filename = path_parts[0]
                uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(png|jpg|jpeg|gif)$'
                return bool(re.match(uuid_pattern, filename, re.IGNORECASE))
        except:
            pass
        return False
    
    def fix_minio_url(self, url: str) -> str:
        """修复 MinIO URL（完整版）"""
        from urllib.parse import urlparse, urlunparse
        
        url = url.strip().strip("'\"`").strip()
        
        if not url.startswith(("http://", "https://")):
            if any(url.startswith(p) for p in ["114.66.47.144", "localhost", "127.0.0.1"]):
                url = f"http://{url}"
        
        try:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.lstrip("/").split("/") if p]
            
            if len(path_parts) == 1:
                filename = path_parts[0]
                new_path = f"/{default_bucket}/{default_chat_path}/{filename}"
                url = urlunparse(parsed._replace(path=new_path))
            elif len(path_parts) >= 1 and path_parts[0] == default_bucket:
                if len(path_parts) == 2:
                    new_path = f"/{default_bucket}/{default_chat_path}/{path_parts[1]}"
                    url = urlunparse(parsed._replace(path=new_path))
        except Exception:
            pass
        
        return url


_chart_service: ChartService | None = None


def get_chart_service() -> ChartService:
    """获取图表服务实例"""
    global _chart_service
    if _chart_service is None:
        _chart_service = ChartService()
    return _chart_service