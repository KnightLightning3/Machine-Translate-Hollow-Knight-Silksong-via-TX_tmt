# export.py
import os
import json
from localization_core import (
    init_config, get_config, 
    read_and_parse_txt, simple_detect_file_language, 
    TextAssetInfo
)
from collections import defaultdict
# from typing import List, Dict

import UnityPy
import subprocess
import shutil
import xml.etree.ElementTree as ET
import re
from typing import List, Tuple, Dict, Union, Any

# 初始化配置
init_config()
# --- 配置常量 ---
FALLBACK_VERSION = '6000.0.50f1' 
ASSET_FILE_PATH = "resources.assets"
DECRYPTOR_EXE = "HollowKnight_TextAssetDecryptor.exe"

# 临时目录
TEMP_BASE_DIR = "temp_hk_modding"
INPUT_BASE64_DIR = os.path.join(TEMP_BASE_DIR, "input_base64")
OUTPUT_DECRYPTED_DIR = os.path.join(TEMP_BASE_DIR, "output_decrypted")
OUTPUT_ENCRYPTED_DIR = os.path.join(TEMP_BASE_DIR, "output_encrypted")
FINAL_OUTPUT_ASSET = "resources_new.assets"

def export_localization_data(files: List[str]):
    """
    遍历所有解密文件，识别 ZH/EN 条目，并保存为 JSON 文件。
    """
    print("\n--- 阶段 1：导出待翻译数据 ---")
    
    all_mapped_entries: Dict[str, Dict[str, TextAssetInfo]] = defaultdict(dict)
    
    print(f"  -> 正在解析 {len(files)} 个文件...")
    
    # 1. 解析所有文件并识别语言
    for filepath in files:
        entries_list = read_and_parse_txt(filepath)
        if not entries_list:
            continue
            
        file_lang = simple_detect_file_language(entries_list)
        
        # 仅处理英文和中文文件
        if file_lang not in {'EN', 'ZH'}:
            continue
        
        # 填充映射字典
        for entry_info in entries_list:
            key = entry_info.key
            if key and entry_info.text.strip():
                entry_info.language = file_lang
                all_mapped_entries[key][file_lang] = entry_info

    # 2. 构建导出列表并应用白名单
    export_list = []
    
    for key, lang_map in all_mapped_entries.items():
        
        # 白名单过滤
        if get_config('ENABLE_WHITELIST_MODE') and key not in get_config('TRANSLATION_WHITELIST_SET'):
            continue
            
        # 筛选出需要翻译的 EN -> ZH 对
        if 'EN' in lang_map and 'ZH' in lang_map:
            en_entry = lang_map['EN']
            zh_entry = lang_map['ZH']

            # 只有英文文本非空且不等于中文文本时才导出
            if en_entry.text.strip() and en_entry.text != zh_entry.text:
                export_list.append({
                    "key": key,
                    "en_filepath": en_entry.filepath,
                    "zh_filepath": zh_entry.filepath,
                    "original_en_text": en_entry.text.strip(),
                    "original_zh_text": zh_entry.text.strip(),
                    "translated_text": "" # 初始翻译结果为空
                })
            
    print(f"  -> 成功识别并导出 {len(export_list)} 个待翻译条目。")
    
    # 3. 写入 JSON 文件
    output_file = "./data/" + get_config('EXPORT_FILE_NAME')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_list, f, ensure_ascii=False, indent=4)
        
    print(f"  -> 数据已保存到 {output_file}。")
    return output_file

# --- 主执行逻辑 ---
if __name__ == "__main__":
    
    # 加载文件
    UnityPy.config.FALLBACK_UNITY_VERSION = FALLBACK_VERSION
    env = UnityPy.load(ASSET_FILE_PATH)
    print(f"✅ {ASSET_FILE_PATH} 加载成功。")

    DECRYPTED_DIR = get_config('DECRYPTED_FILES_DIR')
    
    if not os.path.isdir(DECRYPTED_DIR):
        print(f"[错误] 目录 {DECRYPTED_DIR} 不存在。请检查 config.json。")
        exit(1)
        
    all_decrypted_files = [
        os.path.join(DECRYPTED_DIR, f) 
        for f in os.listdir(DECRYPTED_DIR) 
        if f.endswith(".txt") # 假设你的解密文件都是 .txt
    ]
    
    if not all_decrypted_files:
         print(f"[警告] 目录 {DECRYPTED_DIR} 中未找到任何 .txt 文件。")
         
    export_localization_data(all_decrypted_files)