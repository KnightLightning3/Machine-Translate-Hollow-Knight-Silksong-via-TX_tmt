# translate.py
import json
import os
import re # 需要导入 re 模块
from typing import List, Dict, Any
from tqdm import tqdm
from localization_core import (
    init_config, get_config,find_latest_translation_file,translate_entries_batch
)
import pandas as pd
# 确保在任何函数调用前初始化配置
init_config()
def fix_translation_errors_fallback(
    error_file: str, 
    error_version: int, 
    fallback_version: int,
    error_marker: str = "&&error&&"
) -> str:
    """
    读取包含错误的当前翻译文件 (error_file)，并从上一个成功版本 (fallback_version) 
    中读取对应的 translated_text 来替换错误标识符。
    """
    
    output_file_format = get_config('TRANSLATED_FILE_FORMAT')
    output_file = output_file_format.format(error_version + 1) # 新版本号是当前错误版本的下一个
    
    fallback_file = output_file_format.format(fallback_version)
    
    print(f"\n---阶段 3：修复翻译错误 (版本 {error_version + 1})---")
    print(f"  -> 错误文件 (当前版本): {error_file}")
    print(f"  -> 回退文件 (上一个成功版本): {fallback_file}")
    print(f"  -> 输出文件 (修复后): {output_file}")
    
    if not os.path.exists(error_file):
        print(f"  [错误] 错误输入文件 {error_file} 不存在。")
        return ""
    if not os.path.exists(fallback_file):
        print(f"  [错误] 修复回退文件 {fallback_file} 不存在。无法执行回退修复。")
        # 此时应该报错或要求用户执行全量重译，这里简单返回
        return ""

    # 1. 读取当前包含错误的文件 (当前版本)
    with open(error_file, 'r', encoding='utf-8') as f:
        current_data: List[Dict[str, Any]] = json.load(f)

    # 2. 读取上一个成功的翻译文件 (回退版本)
    with open(fallback_file, 'r', encoding='utf-8') as f:
        fallback_data: List[Dict[str, Any]] = json.load(f)

    if len(current_data) != len(fallback_data):
        print(f"  [警告] 错误文件 ({len(current_data)}) 和回退文件 ({len(fallback_data)}) 条目数不匹配。跳过修复。")
        # 如果条目数不一致，则不能安全地按索引回退
        return error_file
    
    total_fixed_count = 0
    
    # 3. 遍历当前文件，并从回退文件中复制正确值
    # 由于假设顺序严格一致，我们按索引遍历
    for i in tqdm(range(len(current_data)), desc="修复错误条目"):
        current_item = current_data[i]
        
        # 检查当前条目的 translated_text 是否包含错误标识符
        if error_marker in current_item.get('translated_text', ''):
            
            # 从上一个版本中获取对应的 translated_text
            fallback_text = fallback_data[i].get('translated_text')
            
            if fallback_text and error_marker not in fallback_text:
                # 仅在回退文本本身不是错误时才进行替换
                current_item['translated_text'] = fallback_text
                total_fixed_count += 1
            else:
                # 如果回退文本也包含错误标识符，打印警告或保持原样
                print(f"\n  [警告] 索引 {i} 的回退文本也包含错误标识符或为空。保持错误。")


    if total_fixed_count == 0:
        print("-> 未发现需要修复的错误标识符，无需执行修复操作。")
        # 此时应该返回原文件路径
        return error_file 

    print(f"-> 成功修复 {total_fixed_count} 个错误条目。")
    
    # 4. 保存修复后的结果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(current_data, f, ensure_ascii=False, indent=4)
        
    print(f"-> 翻译修复结果已保存到 {output_file}。")
    return output_file
def translate_exported_data(input_file: str, next_version: int,from_lang: str, to_lang: str) -> str:
    """
    读取指定的 JSON 文件进行翻译，并保存为新的版本文件。
    """
    
    output_file_format = get_config('TRANSLATED_FILE_FORMAT')
    output_file = "./data/"+output_file_format.format(next_version) 
    
    # print(f"\n---阶段 2：执行翻译 (版本 {next_version})---")
    print(f"  -> 输入文件: {input_file}")
    print(f"  -> 输出文件: {output_file}")
    
    if not os.path.exists(input_file):
        print(f"  [错误] 翻译输入文件 {input_file} 不存在。请先运行 export.py。")
        return ""

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_items = len(data)
    print(f"-> 准备翻译 {total_items} 个条目...")

    is_initial_translation = (next_version == 1)

    if is_initial_translation:
        # 策略 1: 首次翻译 (V1) - EN -> ZH
        data_transed = translate_entries_batch(data, 'en', 'zh', source_key='original_en_text')
        #制作一个二次翻译字段保存首次翻译结果
        for item in data:
            item['translated_text'] = item.get('secondary_translated_text')
    else:
        # 策略 3: 迭代翻译 (V2+) - from_lang -> to_lang
        #将上一个版本的'secondary_translated_text'结果作为'translated_text'
        for item in data:
            item['translated_text'] = item.get('secondary_translated_text')
        data_transed = translate_entries_batch(data, from_lang , to_lang, source_key='translated_text') # 结果保存在'secondary_translated_text'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data_transed, f, ensure_ascii=False, indent=4)
        
    print(f"-> 翻译结果已保存到 {output_file}。")
    return output_file

if __name__ == "__main__":
    #加载翻译顺序表
    df_trans_loop = pd.read_csv("翻译顺序.csv")
    
    # 1. 查找最新的文件
    # 2. 调用翻译函数
    print(f"--------程序启动--------")
    for _ in range(1):
        # 1. 查找最新的文件
        input_file, latest_version,next_version = find_latest_translation_file()
        # 取得本轮翻译的要求
        from_lang, to_lang = df_trans_loop['翻译源'][next_version-1],df_trans_loop['翻译目标'][next_version-1]
        if next_version == df_trans_loop['版本'][next_version-1]:
            print(f"----开始翻译版本:v{next_version},翻译语言: {from_lang} -> {to_lang}----")
            # 2. 调用翻译函数
            translate_exported_data(input_file, next_version,from_lang, to_lang)
        else:
            print(f"未找到对应版本号:{next_version},错误退出。")
            exit(1)
        break
