# import_data.py
import json
import os
import re
import shutil # 用于文件操作，如复制/清理
import subprocess
from localization_core import (
    init_config, get_config, find_latest_translation_file 
)
from collections import defaultdict
from typing import List, Dict, Any,Tuple
import UnityPy 
import xml.etree.ElementTree as ET

init_config()
DECRYPTED_FILES_DIR = get_config('DECRYPTED_FILES_DIR')
ENCRYPTED_BASE64_DIR = get_config('ENCRYPTED_BASE64_DIR')


def parse_path_id_from_filename(filename: str) -> str:
    """
    从形如 'Asset_46_46_base64.txt' 的文件名中解析出 Path ID (例如 '46')。
    """
    match = re.match(r'Asset_(\d+)_', filename)
    if match:
        return match.group(1)
    # 对于不符合命名规范的文件，返回 None 或空字符串
    return None
def run_decryptor(input_dir, output_dir, mode):
    """
    调用 HollowKnight_TextAssetDecryptor.exe 进行解密或加密。
    
    :param input_dir: 输入目录 (-d)
    :param output_dir: 输出目录 (-o)
    :param mode: 操作模式 ('-d' 解密, '-e' 加密)
    :return: 外部程序运行是否成功 (bool)
    """
    # 确保 DECRYPTOR_EXE 已经被定义为最新的配置值
    global DECRYPTOR_EXE
    DECRYPTOR_EXE = get_config('DECRYPTOR_TOOL_PATH') 
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 构建命令行参数
    command = [
        DECRYPTOR_EXE, 
        mode, input_dir, 
        "-o", output_dir
    ]
    
    try:
        # 使用 subprocess.run 运行外部程序
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True,
            check=False # 即使外部程序返回非零退出码（失败），也不抛出异常
        )
        
        # 检查返回码：0 通常表示成功
        if result.returncode == 0:
            return True
        else:
            print(f"  ❌ 外部工具运行失败 (返回码 {result.returncode})")
            print("  --- 外部工具输出 START ---")
            print(result.stdout)
            print(result.stderr)
            print("  --- 外部工具输出 END ---")
            return False

    except FileNotFoundError:
        print(f"  ❌ 错误: 找不到可执行文件 {DECRYPTOR_EXE}。请确保它在脚本目录下或已添加到系统PATH中。")
        return False
    except Exception as e:
        print(f"  ❌ 运行外部程序时发生错误: {e}")
        return False
def encrypt_modified_assets() -> Dict[str, str]:
    """
    读取外部工具加密修改后的文件，并将翻译后的 .txt 文件复制到加密输入目录。
    """
    encrypted_data = {}
    
    for filename in os.listdir(ENCRYPTED_BASE64_DIR):
        if filename.endswith("_base64.txt"):
            path_id = parse_path_id_from_filename(filename)
            
            if path_id:
                encrypted_filename = os.path.join(ENCRYPTED_BASE64_DIR, filename)
                try:
                    with open(encrypted_filename, 'r', encoding='utf-8') as f:
                        encrypted_base64_string = f.read()
                    
                    # PathID 存储为字符串，与 UnityPy 的 obj.path_id 匹配
                    encrypted_data[path_id] = encrypted_base64_string
                    
                except Exception as e:
                    print(f"  [读取失败] 文件 {filename}: 读取加密文件失败。{e}")

    print(f"  ✅ 成功获取 {len(encrypted_data)} 个 Path ID 的 Base64 加密数据。")
    return encrypted_data
def repack_assets(encrypted_data: Dict[str, str], version: int) -> str:
    """
    使用 UnityPy 将加密后的 Base64 字符串注入 AssetBundle 并保存。
    """
    
    ORIGINAL_ASSET_PATH = get_config('ORIGINAL_ASSET_PATH')
    OUTPUT_ASSET_PATH = get_config('PACKED_ASSET_FORMAT').format(version)
    
    if not os.path.exists(ORIGINAL_ASSET_PATH):
        print(f"  ❌ 错误: 找不到原始资源文件: {ORIGINAL_ASSET_PATH}")
        return ""

    try:
        env = UnityPy.load(ORIGINAL_ASSET_PATH)
    except Exception as e:
        print(f"  ❌ 错误: 无法加载原始资源文件 {ORIGINAL_ASSET_PATH}: {e}")
        return ""

    # 注入加密数据
    for obj in env.objects:
        path_id = str(obj.path_id)
        if path_id in encrypted_data:
            data = obj.read()
            new_encrypted_string = encrypted_data[path_id]
            updated = False
            
            # TextAsset 的两种常见存储方式
            if hasattr(data, 'm_Script'):
                data.m_Script = new_encrypted_string
                updated = True
            elif hasattr(data, 'bytes'):
                data.bytes = new_encrypted_string 
                updated = True
            
            if updated:
                try:
                    # 遵循你提供的 TextAsset 示例，使用 data.save()
                    data.save() 
                except AttributeError:
                    # 某些版本或类型不支持 data.save()，退回到 obj.save(data)
                    try:
                        obj.save(data)
                    except Exception as e:
                        print(f"  ❌ 致命错误：Path ID {path_id} 无法保存: {e}")
                # print(f"  [重新打包] 更新 Path ID: {path_id}", end='\n')

    # 保存新的 Asset Bundle
    with open(OUTPUT_ASSET_PATH, 'wb') as f:
        f.write(env.file.save())
        
    print(f"\n  ✅ 资源打包完成。新文件: {OUTPUT_ASSET_PATH}")
    return OUTPUT_ASSET_PATH
def write_modified_files(translation_results: List[Tuple[str, str, str, str]]):
    """
    将新翻译的文本写入对应的中文 TXT 文件中。

    :param translation_results: 步骤 3 得到的 (entry name, 中文文件名, 原始中文文本, 新中文文本) 列表。
    """
    
    
    files_to_update: Dict[str, Dict[str, str]] = defaultdict(dict)
    
    # 1. 整理需要更新的 Key-Value 对，按文件名分组
    for key, zh_file, original_text, new_text in translation_results:
        files_to_update[zh_file][original_text] = new_text

    # 2. 遍历每个需要更新的文件
    for filename, text_map in files_to_update.items():
        filepath = filename
        if not os.path.exists(filepath):
            print(f"  ❌ 错误: 文件 {filepath} 不存在，跳过写入。")
            continue
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            original_content = content
            
            # 遍历并替换文件中的所有原始文本
            # for original_text, new_text in text_map.items():
            #     print(original_text)
                # 注意：这里我们使用字符串替换。如果原始文本包含特殊字符或 XML 实体，
                # 最好在步骤 3 就直接操作 XML 元素 (如果使用类封装的话)。
                # 鉴于你之前发现的结构，这里尝试精确替换：
                
                # 查找原始的 <entry name="KEY">ORIGINAL_TEXT</entry> 结构
                # 并替换其中的 ORIGINAL_TEXT
                # 我们假设 <entry> 标签体就是原始文本
                
                # 安全替换：查找并替换 XML 标签内的内容
                # 由于我们只关心中文文件，并且假设它们已经被解密为纯文本XML
                # 我们可以尝试查找并替换整个 <entry> 标签体
                
                # 查找 pattern：<entry name="KEY">ORIGINAL_TEXT</entry>
                # 我们必须再次解析 XML 来保证修改的精准性。
                # 由于我们在 read_and_parse_txt 中没有保存 XML 元素，我们必须重新加载。

            # 重新加载 XML，并进行精准修改
            tree = ET.parse(filepath)
            root = tree.getroot()
            modified = False
            
            for entry in root.findall('entry'):
                key = entry.get('name')
                
                for k, original_text, new_text in [(t[0], t[2], t[3]) for t in translation_results if t[1] == filename]:
                    if key == k:
                        entry.text = new_text
                        modified = True
                        # if entry.text.strip() == original_text.strip():
                        #     entry.text = new_text
                        #     modified = True
                        # else:
                        #     # 警告：Key 匹配，但文本内容不匹配，可能是代码逻辑错误或文件已修改
                        #     print(f"  ⚠️ 警告: Key {key} 内容不匹配，跳过替换。")
            
            if modified:
                tree.write(filepath, encoding='utf-8', xml_declaration=True)
                # print(f"  [写入成功] 文件 {filename} 已更新。")
                
        except Exception as e:
            print(f"  ❌ 写入文件 {filename} 时发生错误: {e}")

# --- 主执行逻辑 ---
if __name__ == "__main__":
    # 必须在开头初始化配置
    init_config()
    # 1. 查找最新版本的翻译文件
    translated_json_file, latest_version,_ = find_latest_translation_file()
    print(f"---1. 查找最新版本的翻译文件,文件版本:{latest_version}---")
    with open(translated_json_file, 'r', encoding='utf-8') as f:
        translated_data = json.load(f)

    # 2. 按原始文件路径分组翻译结果
    translation_results = []
    for item in translated_data:
        # 确保有新的翻译文本
        #  (entry name, 中文文件名, 原始中文文本, 新中文文本)
        translation_item = (
            item['key'],
            item['zh_filepath'],
            item['original_zh_text'],
            item['secondary_translated_text']
        )
        translation_results.append(translation_item)
    print(f"---2.写入结果到明码txt文件---")
    write_modified_files(translation_results) # 写入结果到文件

    print(f"---3.运行外部加密工具---")
    if not run_decryptor(DECRYPTED_FILES_DIR, ENCRYPTED_BASE64_DIR, "-e"):
        print("  ❌ 加密步骤失败，跳过重新打包。")
    else:
        print("加密成功")

    print("---4.准备加密和获取 Base64 字符串---")
    encrypted_data = encrypt_modified_assets()
    
    # 5. 打包 (保持不变)
    print("---5.重新打包 Asset Bundle---")
    if encrypted_data:
        _, latest_version,_ = find_latest_translation_file()
        packed_asset_path = repack_assets(encrypted_data, latest_version)
    else:
        print("[提示] 没有翻译数据需要重新打包。")
    print(f"打包完成,文件名{packed_asset_path}")
