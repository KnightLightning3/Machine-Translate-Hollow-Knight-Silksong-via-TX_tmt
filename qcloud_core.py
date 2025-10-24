# qcloud_core.py
import json
import requests
import time
import hashlib
import hmac
from datetime import datetime
from typing import List, Dict, Any, Tuple
import sys
from tqdm import tqdm
if sys.version_info[0] <= 2:
    from httplib import HTTPSConnection
else:
    from http.client import HTTPSConnection
# 假设 localization_core 中的 get_config 已经可以导入
# 实际上在模块间调用时，我们必须通过参数传递或让调用者提供配置。
# 为了保持 qcloud_core 的独立性，我们将配置值作为参数传入。

# --- 腾讯云 V3 签名辅助函数 (来自你的示例代码) ---
def sign(key, msg):
    """计算 HMAC-SHA256 签名"""
    if isinstance(msg, str):
        msg = msg.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).digest()

# --- 腾讯云翻译 API 配置 ---
TMT_MAX_CHAR_COUNT = 1500
TMT_MAX_TEXT_COUNT = 300
TMT_ENDPOINT = "tmt.tencentcloudapi.com"
TMT_VERSION = "2018-03-21"
TMT_ACTION = "TextTranslateBatch"
TMT_SERVICE = "tmt"
TMT_ALGORITHM = "TC3-HMAC-SHA256"


def _get_signed_headers(action: str, payload: str, timestamp: int, region: str, secret_id: str, secret_key: str) -> Dict[str, str]:
    """
    生成腾讯云 API 签名所需的头部信息 (V3 签名核心步骤 1-4)。
    """
    date_utc = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")

    # ************* 步骤 1：拼接规范请求串 *************
    http_request_method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    content_type = "application/json; charset=utf-8"
    
    canonical_headers = "content-type:%s\nhost:%s\nx-tc-action:%s\n" % (content_type, TMT_ENDPOINT, action.lower())
    signed_headers = "content-type;host;x-tc-action"
    hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    
    canonical_request = (http_request_method + "\n" +
                         canonical_uri + "\n" +
                         canonical_querystring + "\n" +
                         canonical_headers + "\n" +
                         signed_headers + "\n" +
                         hashed_request_payload)

    # ************* 步骤 2：拼接待签名字符串 *************
    credential_scope = date_utc + "/" + TMT_SERVICE + "/" + "tc3_request"
    hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = (TMT_ALGORITHM + "\n" +
                      str(timestamp) + "\n" +
                      credential_scope + "\n" +
                      hashed_canonical_request)

    # ************* 步骤 3：计算签名 *************
    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date_utc)
    secret_service = sign(secret_date, TMT_SERVICE)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # ************* 步骤 4：拼接 Authorization *************
    authorization = (TMT_ALGORITHM + " " +
                     "Credential=" + secret_id + "/" + credential_scope + ", " +
                     "SignedHeaders=" + signed_headers + ", " +
                     "Signature=" + signature)

    # ************* 步骤 头部信息 *************
    headers = {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": TMT_ENDPOINT,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": TMT_VERSION,
        "X-TC-Region": region,
    }
    return headers

def _make_tmt_request(TMT_ENDPOINT, headers, payload, delay, texts, attempt_number):
    """
    执行单次腾讯机器翻译（TMT）API 请求。
    如果失败，返回 None 和错误信息。
    如果成功，返回 TargetTextList。
    """
    # return ["哈基米"] * len(texts)
    try:
        response = requests.post(
            f"https://{TMT_ENDPOINT}", 
            headers=headers, 
            data=payload.encode("utf-8"), 
            timeout=30 
        )
        
        time.sleep(delay) # 遵守 API 限制

        resp_json = response.json()
        
        # 1. 检查 HTTP 状态码或 API 响应中的 'Error' 字段
        if response.status_code != 200 or 'Error' in resp_json.get('Response', {}):
            error_msg = resp_json.get('Response', {}).get('Error', {}).get('Message', '未知API错误')
            error_code = resp_json.get('Response', {}).get('Error', {}).get('Code', 'UNKNOWN')
            request_id = resp_json.get('Response', {}).get('RequestId', '无 RequestId')
            
            print(f"  ❌ 尝试 {attempt_number}: API 返回错误 ({error_code}): {error_msg}, request_id: {request_id}")
            return None # 失败返回 None

        # 2. 成功
        return resp_json['Response']['TargetTextList']
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ 尝试 {attempt_number}: 网络请求失败: {e}")
        return None # 失败返回 None
        
    except Exception as e:
        print(f"  ❌ 尝试 {attempt_number}: 发生意外错误: {e}")
        return None # 失败返回 None
    
def tmt_translate_single_batch(
    texts: List[str], from_lang: str, to_lang: str, 
    secret_id: str, secret_key: str, region: str, project_id: int, delay: float
) -> List[str]:
    """
    执行一次腾讯云 API 请求和签名。
    """
    
    timestamp = int(time.time())
    
    payload_data = {
        "Source": from_lang,
        "Target": to_lang,
        "ProjectId": project_id,
        "SourceTextList": texts
    }
    payload = json.dumps(payload_data)
    
    headers = _get_signed_headers(TMT_ACTION, payload, timestamp, region, secret_id, secret_key)
    
    translation_result = _make_tmt_request(TMT_ENDPOINT, headers, payload, delay, texts, attempt_number=1)

    if translation_result is not None:
        # 第一次尝试成功
        # print(f"  ✅ 成功翻译 {len(texts)} 个文本片段。")
        return translation_result
    else:
        # 第一次尝试失败，等待并进行重试
        print("  ⚠️ 第一次尝试失败，等待 10 秒后重试...")
        time.sleep(10)
        
        # 第二次尝试 (重试)
        translation_result = _make_tmt_request(TMT_ENDPOINT, headers, payload, delay, texts, attempt_number=2)

        if translation_result is not None:
            # 第二次尝试成功
            # print(f"  ✅ 成功翻译 {len(texts)} 个文本片段。")
            return translation_result
        else:
            # 第二次尝试仍失败，最终返回错误标记
            print(f"  ❌ 第二次尝试失败，返回错误标记 '&&error&&' * {len(texts)}")
            time.sleep(10) # 最终失败后仍然等待
            return ["&&error&&"] * len(texts)

def tmt_translate_batch(texts: List[str], from_lang: str, to_lang: str, config: Dict[str, Any]) -> List[str]:
    """
    处理整个文本列表的分批和翻译，确保符合 API 限制，并从配置字典中读取参数。
    """
    # for t in texts:
    #     if '=' in t or '#' in t:
    #         print(f"{t}包含特殊符号，停止翻译")
    #         exit(1)
    # return texts
    secret_id = config.get('Tencent_Secret_Id')
    secret_key = config.get('Tencent_Secret_Key')
    region = config.get('Tencent_Region')
    project_id = config.get('Tencent_Project_ID')
    delay = config.get('API_DELAY_SECONDS') # 假设这些值都有合理的默认值或已在调用方验证

    if not secret_id or not secret_key:
        print("  ❌ 错误：Tencent_Secret_Id 或 Tencent_Secret_Key 配置缺失。")
        return ["CONFIG_ERROR"] * len(texts) if texts else []
        
    all_translated_texts = []
    current_batch_texts = []
    current_batch_char_count = 0
    text_len = sum([len(text) for text in texts])
    print(f"➡️➡️➡️ 总文本长度: {text_len} 字符, 分批翻译中...")
    progress_bar = tqdm(texts, desc="翻译文本片段", unit="片段", leave=True)
    for text in progress_bar:
    # for text in texts:
        text_len = len(text)
        # 检查是否需要发送当前已累积的批次 (当前文本的加入会导致超限)
        # 注意：这里是检查 *加入当前文本* 是否会导致超限，如果是，则先发送当前批次。
        # 实际更严谨的做法是：如果当前批次已满（达到 TMT_MAX_TEXT_COUNT），或者
        # 加上当前文本后会超过 TMT_MAX_CHAR_COUNT，就发送旧批次。
        # 优化判断逻辑: 如果当前批次已满（> TMT_MAX_TEXT_COUNT - 1），或者加上当前文本后会超长
        if (len(current_batch_texts) >= TMT_MAX_TEXT_COUNT or
            (current_batch_char_count + text_len > TMT_MAX_CHAR_COUNT and current_batch_texts)): 
            
            # 如果批次非空，则发送当前批次
            if current_batch_texts:
                translated_batch = tmt_translate_single_batch(
                    current_batch_texts, from_lang, to_lang, 
                    secret_id, secret_key, region, project_id, delay
                )
                all_translated_texts.extend(translated_batch)
                
                # 重置批次
                current_batch_texts = []
                current_batch_char_count = 0
            
        
        # ***** 修正点：将当前文本添加到批次 *****
        current_batch_texts.append(text)
        current_batch_char_count += text_len
    # 发送最后一个批次
    if current_batch_texts:
        translated_batch = tmt_translate_single_batch(
            current_batch_texts, from_lang, to_lang,
            secret_id, secret_key, region, project_id, delay # <-- **修正：现在传递所有参数**
        )
        all_translated_texts.extend(translated_batch)

    return all_translated_texts