import json
import os
import re
import requests
import time
import random
import hashlib
from typing import List, Tuple, Dict
from collections import defaultdict
from typing import List, Tuple, Dict, Any # 引入 Any
from qcloud_core import tmt_translate_batch
# --- 全局配置变量，将在 init_config 中加载 ---
_CONFIGURATION = {}
def init_config(config_file="config.json"):
    """加载配置并初始化白名单。"""
    global _CONFIGURATION
    
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"配置文件 {config_file} 未找到。")
        
    with open(config_file, 'r', encoding='utf-8') as f:
        _CONFIGURATION = json.load(f)  
    # 加载白名单
    whitelist_file = _CONFIGURATION.get("WHITELIST_FILE_PATH", "whitelist.txt")
    if os.path.exists(whitelist_file):
        TRANSLATION_WHITELIST = []
        try:
            with open(whitelist_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.split('#', 1)[0].strip()
                    if line:
                        TRANSLATION_WHITELIST.append(line)
        except Exception as e:
            print(f"  [错误] 读取白名单文件失败: {e}。将禁用白名单。")

        TRANSLATION_WHITELIST_SET = set(TRANSLATION_WHITELIST)
        ENABLE_WHITELIST_MODE = len(TRANSLATION_WHITELIST_SET) > 0
        if ENABLE_WHITELIST_MODE:
            print(f"  [配置] 已启用白名单模式，包含 {len(TRANSLATION_WHITELIST_SET)} 个条目。")
    else:
        print("  [配置] 未找到白名单文件，白名单模式禁用。")

def get_config(key: str = None):
    """获取整个配置字典或单个配置值。"""
    if key is None:
        return _CONFIGURATION
    return _CONFIGURATION.get(key)
# --- 核心常量 ---
# 特殊字符分隔符（包含编码和非编码，以及数字占位符）
# ENCODED_DELIMITER_TAGS = r'(&lt;br&gt;|&lt;page&gt;|&lt;hpage&gt;|<br>|<hpage>|<page>|&lt;page=M&gt;|"&lt;page=S&gt;|&lt;page=B&gt;)'
# ENCODED_DELIMITER_TAGS = r'(&lt;[a-zA-Z0-9_/]+&gt;|<br>|<hpage>|<page>)'
ENCODED_DELIMITER_TAGS = r'(&lt;[a-zA-Z0-9_/=]+&gt;|&amp;lt;[a-zA-Z0-9_/=]+&amp;gt;|<br>|<hpage>|<page>|&amp;#\d+;|&amp;)'
OTHER_DELIMITERS = r'(&amp;#[0-9]+;|{[0-9]+})'
DELIMITERS = re.compile(f'({ENCODED_DELIMITER_TAGS}|{OTHER_DELIMITERS})', re.IGNORECASE)

PUNC_MARK= {  # 标点替换
    "&#8220;" : "“",
    "&#8221;" : "”",
    '&amp;#8217;' : "’",
    '&amp;#8216;' : "‘",
    '&#8217;' : "’",
    '&#8216;' : "‘",
}
# ------------------

# TextAssetInfo 类定义
class TextAssetInfo:
    def __init__(self, key: str, text: str, filepath: str, language: str = 'UNKNOWN'):
        self.key = key
        self.text = text
        self.filepath = filepath
        self.language = language

    def to_dict(self):
        return self.__dict__

# --- 语言检测函数 ---
def simple_detect_file_language(entries_list: List[TextAssetInfo]) -> str:
    """
    根据文件中所有条目聚合的字符特征，快速判断文件的语言。

    :param entries_list: 文件中所有 TextAssetInfo 对象的列表。
    :return: 文件的语言代码 ('ZH', 'JP', 'KO', 'RU', 'PT', 'EN', 'UNKNOWN')。
    """
    if not entries_list:
        return 'UNKNOWN'

    # 聚合所有非空文本
    full_text = " ".join(e.text for e in entries_list if e.text.strip())
    
    # 设定一个阈值，例如至少需要 5 个特征字符
    THRESHOLD = 3

    # 使用 Python 的 in 操作符进行简单、高效的字符串包含检查
    if 'Act1Start' in full_text:
        return 'EN'
    if 'Full Chamber to the kingdom of the White Wyrm' in full_text:
        return 'EN'
    if 'The blade is honed to a fine edge' in full_text:
        return 'EN'
    # --- 3. 日文 (JP) ---
    # 平假名/片假名：优先识别日文的独有字符
    # 范围: \u3040-\u309F (平假名) 和 \u30A0-\u30FF (片假名)
    if len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF]', full_text)) > 3:
        return 'JP'
    # --- 4. 中文 (ZH) ---
    # 汉字：最后检查汉字，因为它与日文有重叠，但日文假名优先排除
    # 范围: \u4e00-\u9fff
    if len(re.findall(r'[\u4e00-\u9fff]', full_text)) > 1:
        return 'ZH'
    # --- 1. 韩语 (KO) ---
    # 谚文 (Hangul) 范围: \uac00-\ud7af
    if len(re.findall(r'[\uac00-\ud7af]', full_text)) >= 1:
        return 'KO'
    
    # --- 2. 俄语 (RU) ---
    # 西里尔字母 (Cyrillic) 范围: \u0400-\u04ff
    if len(re.findall(r'[\u0400-\u04ff]', full_text)) >= 1:
        return 'RU'
    
    # --- 3. 希腊语 (EL/GR) --- 【新增部分】
    # 希腊字母范围: \u0370-\u03ff
    greek_chars = re.findall(r'[\u0370-\u03ff]', full_text)
    if len(greek_chars) >= 1:
        return 'EL'

    # --- 5. 葡萄牙语 (PT) ---
    # 特殊拉丁字符
    pt_chars = re.findall(r'[ãõçáéíóúàèìòùäüßö]', full_text, re.IGNORECASE)
    if len(pt_chars) >= 1:
        return 'PT'

    # --- 6. 英文/其他 (EN) ---
    # 如果文本足够长（比如 50 个字符以上），且没有检测到上述特征，默认为英文。
    if len(full_text.strip()) > 1:
        return 'EN'

    return 'UNKNOWN'

# --- 百度翻译核心函数 ---
def baidu_translate_single_batch(texts: List[str], from_lang: str, to_lang: str) -> List[str]:
    # ... (与你之前的实现相同，包含 "哈基米" 错误返回逻辑) ...
    
    APP_ID = get_config('Baidu_APP_ID')
    API_KEY = get_config('Baidu_API_KEY')
    DELAY = get_config('API_DELAY_SECONDS')
    
    if not texts:
        return []

    ERROR_PLACEHOLDER = ["哈基米"] * len(texts) 
    # return ERROR_PLACEHOLDER
    
    time.sleep(DELAY) # 强制延时以遵守 QPS 限制

    query = "\n".join(texts)
    salt = str(random.randint(32768, 65536))
    sign = hashlib.md5((APP_ID + query + salt + API_KEY).encode()).hexdigest()

    # ... (API 请求和错误处理逻辑保持不变) ...
    URL = 'http://api.fanyi.baidu.com/api/trans/vip/translate'
    payload = {'appid': APP_ID, 'q': query, 'from': from_lang, 'to': to_lang, 'salt': salt, 'sign': sign}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        r = requests.post(URL, params=payload, headers=headers, proxies=None)
        r.raise_for_status() 
        result = r.json()
        
        if 'trans_result' in result:
            return [item['dst'] for item in result['trans_result']]
            
        elif 'error_code' in result:
            if result['error_code'] == '54003':
                 print("  ❌ 百度翻译 API 错误：QPS 限制触发！请检查延时设置。")
            else:
                 print(f"  ❌ 百度翻译 API 错误：{result['error_code']} - {result.get('error_msg', '未知错误')}")
            return ERROR_PLACEHOLDER 
            
        else:
            print(f"  ❌ 百度翻译 API 响应格式错误：{result}")
            return ERROR_PLACEHOLDER

    except requests.exceptions.RequestException as e:
        print(f"  ❌ 百度翻译请求失败: {e}")
        return ERROR_PLACEHOLDER
        
    except Exception as e:
        print(f"  ❌ 翻译过程中发生未知错误: {e}")
        return ERROR_PLACEHOLDER
# 字符解码和编码
def _encode_text(text: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    对单个文本进行分段和编码，生成纯文本片段和重构映射表。
    使用 re.finditer 手动控制分词，避免 re.split 产生空字符串和重复。
    
    :return: (纯文本片段列表, 重构映射表)
    """
    if not text.strip():
        return [], []
    
    # 预处理：将双重编码实体解码为字符，以便翻译时被视作普通标点
    decoded_text = text
    for item in PUNC_MARK:
        decoded_text = decoded_text.replace(item, PUNC_MARK[item])

    # decoded_text = text.replace('&amp;#8217;', '’') 
    # decoded_text = decoded_text.replace('&#8217;', '’')
    # decoded_text = decoded_text.replace('&amp;#8216;', '‘') 
    # decoded_text = decoded_text.replace('&#8216;', '‘')
    
    
    text_to_translate: List[str] = []
    reconstruction_map: List[Tuple[str, str]] = []
    
    last_end = 0
    
    # 遍历所有匹配到的分隔符
    for match in DELIMITERS.finditer(decoded_text):
        start, end = match.span()
        delimiter_value = match.group(0) # 获取匹配到的整个分隔符字符串

        # 1. 提取匹配项之前的“文本片段”
        # 提取从上一个匹配项结束位置到当前匹配项开始位置之间的文本
        text_segment = decoded_text[last_end:start]
        
        # 只有在文本片段非空时才处理
        if text_segment:
            stripped_segment = text_segment.strip()
            
            # 如果 strip 后还有内容，则这是一个需要翻译的文本片段
            if stripped_segment:
                text_to_translate.append(stripped_segment)
                # 映射表存储原始片段 (保留空格)
                reconstruction_map.append(('T', text_segment))
            else:
                # 如果是纯空格（如 "  "），将其视为分隔符（D）保留
                reconstruction_map.append(('D', text_segment))
                
        # 2. 提取分隔符本身
        # 避免连续分隔符时产生重复，因为这里是按 finditer 的结果逐个处理的
        reconstruction_map.append(('D', delimiter_value))
        
        # 更新上一个匹配项的结束位置
        last_end = end

    # 3. 处理最后一个分隔符之后的“尾部文本”
    tail_segment = decoded_text[last_end:]
    if tail_segment:
        stripped_segment = tail_segment.strip()
        
        if stripped_segment:
            text_to_translate.append(stripped_segment)
            reconstruction_map.append(('T', tail_segment))
        else:
            # 尾部是纯空格
            reconstruction_map.append(('D', tail_segment))
    
    # 注意：我们不再需要 _decode_text 中那些处理空格的复杂逻辑，因为空格已被包含在 'T' 或 'D' 片段中。
    return text_to_translate, reconstruction_map
def _decode_text(translated_texts: List[str], reconstruction_map: List[Tuple[str, str]]) -> str:
    """
    使用翻译结果和映射表重构单个文本。
    :param translated_texts: 纯文本片段的翻译结果列表。
    :param reconstruction_map: 重构映射表。
    :return: 最终的重构文本。
    """
    translated_index = 0
    final_parts = []
    for type, value in reconstruction_map:
        if type == 'D':
            final_parts.append(value)
        else:
            if translated_index < len(translated_texts):
                final_parts.append(translated_texts[translated_index])
                translated_index += 1
                
    final_result = "".join(final_parts)
    
    return final_result
def translate_entries_batch(entry_list: List[Dict[str, Any]], from_lang: str, to_lang: str, source_key: str = None) -> List[Dict[str, Any]]:
    """
    【批量翻译核心函数】
    对整个 entry 列表进行批量分段、翻译和重构。

    :param entry_list: 待翻译的条目列表 (来自 JSON 文件)。
    :param from_lang: 源语言代码。
    :param to_lang: 目标语言代码。
    :return: 包含翻译结果的条目列表。
    """
    # -----------------------------------------------------------
    # 阶段 1: 全局分段和编码
    # -----------------------------------------------------------
    global_pure_text_list = []
    global_reconstruction_maps = []
    global_text_pointer = [] # 记录每个 entry 对应 pure_text_list 的起始索引

    for entry in entry_list:
        if source_key == 'original_en_text':
            source_text = entry['original_en_text']
        elif source_key == 'translated_text':
            source_text = entry.get('translated_text')
        # elif source_key == 'translated_en_text_temp': # 用于 ZH->EN->ZH 循环的中间 EN 结果
        #     source_text = entry.get('translated_en_text_temp')

        # if from_lang == 'en':
        #     source_text = entry['original_en_text']
        # else:
        #     # 迭代翻译时，我们使用上一个版本的中文翻译结果
        #     source_text = entry.get('translated_zh_text') or entry['original_zh_text']
            
        pure_texts, mapping = _encode_text(source_text)
        
        global_text_pointer.append(len(global_pure_text_list)) # 记录该 entry 的起始索引
        global_pure_text_list.extend(pure_texts)
        global_reconstruction_maps.append(mapping)
    
    if not global_pure_text_list:
        print("  [警告] 待翻译的纯文本列表为空。")
        return entry_list

    # -----------------------------------------------------------
    # 阶段 2: 批量翻译 (调用腾讯云 API)
    # -----------------------------------------------------------
    print(f"  -> 总共需要翻译 {len(global_pure_text_list)} 个文本片段。")

    # 从配置中获取所有需要的参数，并以字典形式传递给 qcloud_core
    config_for_qcloud = {
        'Tencent_Secret_Id': get_config('Tencent_Secret_Id'),
        'Tencent_Secret_Key': get_config('Tencent_Secret_Key'),
        'Tencent_Region': get_config('Tencent_Region'),
        'Tencent_Project_ID': get_config('Tencent_Project_ID'),
        'API_DELAY_SECONDS': get_config('API_DELAY_SECONDS'),
    }
    
    # 假设 tmt_translate_batch 会处理分批和限制，并返回一个完整的翻译结果列表
    translated_pure_text_list = tmt_translate_batch(
        global_pure_text_list, 
        from_lang, 
        to_lang,
        config_for_qcloud # 传递配置字典
    )

    if len(translated_pure_text_list) != len(global_pure_text_list):
        print("  [严重错误] API 返回的翻译片段数量与发送数量不匹配！跳过重构。")
        return entry_list
    
    # -----------------------------------------------------------
    # 阶段 3: 全局重构和解码
    # -----------------------------------------------------------
    
    for i, entry in enumerate(entry_list):
        start_index = global_text_pointer[i]
        mapping = global_reconstruction_maps[i]
        # 确定该 entry 包含多少个纯文本片段
        if i + 1 < len(global_text_pointer):
            end_index = global_text_pointer[i+1]
        else:
            end_index = len(global_pure_text_list)
        # 提取该 entry 对应的翻译结果片段
        entry_translated_texts = translated_pure_text_list[start_index:end_index]
        # 重构文本
        final_text = _decode_text(entry_translated_texts, mapping)
        entry['secondary_translated_text'] = final_text
        
        # # 将结果写回 entry
        # if to_lang == 'zh':
        #     entry['translated_text'] = final_text
        # elif to_lang == 'en':
        #     # 仅在回译时使用，作为中间结果存储
        #     entry['translated_en_text_temp'] = final_text 

    return entry_list
# ---文件解析函数(保持不变)---
def read_and_parse_txt(filepath: str) -> List[TextAssetInfo]:
    """读取并解析单个 XML 文件，提取所有 <entry> 标签的内容。"""
    entries: List[TextAssetInfo] = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  [错误] 无法读取文件 {filepath}: {e}")
        return entries
    pattern = re.compile(r'<entry\s+name="([^"]+)"\s*>(.*?)</entry>', re.DOTALL | re.IGNORECASE)
    matches = pattern.findall(content)

    for key, text in matches:
        entries.append(TextAssetInfo(
            key=key,
            text=text.strip(),
            filepath=filepath
        ))
    return entries
def find_latest_translation_file() -> tuple[str, int]:
    """
    查找当前目录下最新的翻译结果文件，并返回其路径和版本号。
    返回: (最新的文件路径, 目前版本号)
    """
    format_string = get_config('TRANSLATED_FILE_FORMAT')
    # 转换为正则表达式模式：例如 localization_translated_v(\d+)\.json
    pattern = re.compile(format_string.replace('{}', r'(\d+)').replace('.', r'\.') + '$')
    
    latest_version = 0
    latest_file = get_config('EXPORT_FILE_NAME') # 默认从 export.json 开始

    current_dir = "./data/"
    for filename in os.listdir(current_dir):
        match = pattern.match(filename)
        if match:
            version = int(match.group(1))
            if version > latest_version:
                latest_version = version
                latest_file = filename
    
    # 如果找到了最新的 vN.json，那么下一个输入就是 vN.json，输出是 v(N+1).json
    # 如果没找到，输入是 export.json，输出是 v1.json
    next_version = latest_version + 1
    return current_dir+latest_file, latest_version,next_version
