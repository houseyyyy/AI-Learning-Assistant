# transcriber.py
import sys
from pathlib import Path
project_root = str(Path(__file__).resolve().parent.parent)
sys.path.append(project_root)

import os
import json
import time
import uuid
import base64
import requests
from pydub import AudioSegment
import io
from utils import retry

# 定义可重试的异常类型
RETRYABLE_EXCEPTIONS = (requests.exceptions.RequestException,)
@retry(max_retries=3, delay=5, allowed_exceptions=RETRYABLE_EXCEPTIONS)
def transcribe_single_audio_chunk(audio_path: str, doubao_app_id: str,doubao_token: str) -> str | None:
    """使用豆包语音识别API转录单个音频文件"""
    print(f"  > 正在转录: {os.path.basename(audio_path)}")
    
    try:
        # 1. 准备API请求参数
        task_id = str(uuid.uuid4())
        base64_data, audio_format = read_and_convert_audio(audio_path)
        
        headers = {
            "X-Api-App-Key": doubao_app_id,
            "X-Api-Access-Key": doubao_token,
            "X-Api-Resource-Id": "volc.bigasr.auc",
            "X-Api-Request-Id": task_id,
            "X-Api-Sequence": "-1"
        }

        payload = {
            "user": {"uid": "transcriber_agent"},
            "audio": {
                "data": base64_data,
                "format": audio_format,
                "codec": "raw",
                "rate": 16000,
                "bits": 16,
                "channel": 1
            },
            "request": {
                "model_name": "bigmodel",
                "show_utterances": True,
                "corpus": {"correct_table_name": "", "context": ""}
            }
        }
        
        # 2. 提交转录任务
        submit_url = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
        response = requests.post(submit_url, data=json.dumps(payload), headers=headers)
        
        # 检查提交响应
        if 'X-Api-Status-Code' not in response.headers or response.headers["X-Api-Status-Code"] != "20000000":
            error_msg = f"提交失败: {response.headers.get('X-Api-Message', '未知错误')}"
            print(f"  > ❌ {error_msg}")
            raise Exception(error_msg)
        
        x_tt_logid = response.headers.get("X-Tt-Logid", "")
        print(f"  > ✅ 任务提交成功! Task ID: {task_id}, Log ID: {x_tt_logid}")
        
        # 3. 轮询任务结果
        return poll_transcription_result(task_id, x_tt_logid,doubao_app_id,doubao_token)
    
    except Exception as e:
        print(f"  > ❌ 转录过程中发生错误: {str(e)}")
        raise e

def read_and_convert_audio(audio_path: str):
    """读取并转换音频为API所需格式"""
    try:
        # 读取音频文件
        audio = AudioSegment.from_file(audio_path)
        
        # 转换为API要求的格式: 16kHz采样率, 单声道
        audio = audio.set_frame_rate(16000).set_channels(1)
        
        # 导出为WAV格式到内存缓冲区
        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        
        # 转为Base64编码
        audio_data = wav_buffer.read()
        return base64.b64encode(audio_data).decode('utf-8'), "wav"
        
    except Exception as e:
        print(f"  > ❌ 音频转换失败: {str(e)}")
        raise

def poll_transcription_result(task_id: str, x_tt_logid: str,doubao_app_id: str,doubao_token: str,max_attempts: int = 60, interval: int = 2) -> str:
    """轮询转录结果"""
    query_url = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    
    headers = {
        "X-Api-App-Key": doubao_app_id,
        "X-Api-Access-Key": doubao_token,
        "X-Api-Resource-Id": "volc.bigasr.auc",
        "X-Api-Request-Id": task_id,
        "X-Tt-Logid": x_tt_logid
    }
    
    for attempt in range(1, max_attempts + 1):
        try:
            # 发送查询请求
            response = requests.post(query_url, json.dumps({}), headers=headers)
            
            # 检查响应状态
            status_code = response.headers.get('X-Api-Status-Code', "")
            
            if status_code == '20000000':  # 任务完成
                result = response.json()
                transcript = extract_transcript_text(result)
                print(f"  > ✅ 转录成功! 字符数: {len(transcript)}")
                return transcript
                
            elif status_code in ('20000001', '20000002'):  # 处理中或排队中
                wait_time = interval
                print(f"  > ⌛ 任务处理中 ({attempt}/{max_attempts}), {wait_time}秒后重试...")
                time.sleep(wait_time)
                
            else:  # 任务失败
                error_msg = f"任务失败: {response.headers.get('X-Api-Message', '未知错误')}"
                print(f"  > ❌ {error_msg}")
                raise Exception(error_msg)
                
        except requests.exceptions.RequestException as e:
            print(f"  > ⚠️ 查询失败 (尝试 {attempt}/{max_attempts}): {str(e)}")
            time.sleep(interval)
    
    # 达到最大尝试次数仍未完成
    raise Exception(f"转录任务超时，尝试 {max_attempts} 次后仍未完成")

def extract_transcript_text(api_response: dict) -> str:
    """从API响应中提取转录文本"""
    try:
        # 解析豆包API的响应结构
        utterances = api_response.get('result', {}).get('utterances', [])
        
        # 拼接所有话语
        transcript = "\n".join(
            f"{utt.get('text', '')}"
            for utt in utterances
        )
        
        return transcript
        
    except Exception as e:
        print(f"  > ❌ 解析转录结果失败: {str(e)}")
        raise Exception("无法解析API响应")

# 下面是测试模块功能
# transcript = transcribe_single_audio_chunk("audio.m4a","2958001866","Vv1BBcvq5D-pFrgA76_OR-oXmsK3MJ5t")
# print(transcript)