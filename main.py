import concurrent.futures
import os
import shutil
import yaml  # 导入YAML库
from video_processor.splitter import split_media_to_audio_chunks_generator
from video_processor.transcriber import transcribe_single_audio_chunk
from openai import OpenAI  # 使用与DeepSeek兼容的OpenAI SDK

def main_process_generator(input_path: str, doubao_app_id: str, doubao_token: str, deepseek_api_key: str, output_filename: str, query: str):
    """
    修改版：使用 DeepSeek API 替代 Dify 和 OpenAI，并从外部 YAML 文件加载提示。
    """
    output_dir = "output_chunks"
    final_notes_save_path = f"{output_filename}.md"
    
    video_exts = {'.mp4', '.mov', '.mpeg', '.webm'}
    audio_exts = {'.mp3', '.m4a', '.wav', '.amr', '.mpga'}
    text_exts = {'.txt', '.md', '.mdx', '.markdown', '.pdf', '.html', '.xlsx', '.xls', '.doc', '.docx', '.csv', '.eml', '.msg', '.pptx', '.ppt', '.xml', '.epub'}

    file_ext = os.path.splitext(input_path)[1].lower()
    current_progress = 0
    full_transcript = ""

    # --- 新增: 加载 Prompts 配置文件 ---
    try:
        with open('prompts.yml', 'r', encoding='utf-8') as f:
            prompts_config = yaml.safe_load(f)
    except FileNotFoundError:
        yield "persistent_error", 0, "**配置文件丢失**\n\n无法找到 `prompts.yml` 文件。请确保该文件与脚本位于同一目录。"
        return
    except Exception as e:
        yield "persistent_error", 0, f"**配置文件读取错误**\n\n读取 `prompts.yml` 时发生错误。\n\n**原始错误信息:**\n`{e}`"
        return
    # --- 结束新增 ---

    # --- DeepSeek API 调用函数 ---
    def run_deepseek_and_yield_results():
        """直接调用 DeepSeek API 生成结果"""
        try:
            client = OpenAI(
                api_key=deepseek_api_key,
                base_url="https://api.deepseek.com/v1"
            )
            
            # --- 修改: 从配置文件动态构建提示 ---
            query_key = query.lower()
            
            # 检查请求的操作类型是否有效
            if query_key not in prompts_config['user_prompts']:
                valid_options = list(prompts_config['user_prompts'].keys())
                yield "persistent_error", 0, f"**无效的操作类型**\n\n请求的操作 '{query}' 不是一个有效的选项。有效选项为: {valid_options}"
                return

            # 获取对应的 system role 和 user prompt 模板
            system_role = prompts_config['system_roles'].get(query_key, "你是一个通用的AI助手。")
            user_prompt_template = prompts_config['user_prompts'][query_key]
            
            # 将文本内容替换到模板的占位符中
            prompt = user_prompt_template.replace('{{transcript}}', full_transcript)
            # --- 结束修改 ---
            
            # 调用 DeepSeek API（流式响应）
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_role},
                    {"role": "user", "content": prompt}
                ],
                stream=True,
                max_tokens=4000,
                temperature=0.7
            )
            
            # 处理流式响应
            collected_messages = []
            
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    message_text = chunk.choices[0].delta.content
                    collected_messages.append(message_text)
                    yield "llm_chunk", message_text
            
            # 保存完整响应
            full_response = ''.join(collected_messages)
            try:
                with open(final_notes_save_path, 'w', encoding='utf-8') as f:
                    f.write(full_response)
                yield "save_path", final_notes_save_path
            except IOError as e:
                user_friendly_error = f"**保存最终文件失败**\n\n无法将生成的内容写入本地文件。\n\n**原始错误信息:**\n`{e}`"
                yield "persistent_error", 0, user_friendly_error
        
        except Exception as e:
            error_type = type(e).__name__
            if "Authentication" in error_type or "401" in str(e):
                user_friendly_error = "**认证失败**\n\nDeepSeek API密钥无效或过期。请检查您的API密钥配置。"
            elif "RateLimit" in error_type:
                user_friendly_error = "**请求限制**\n\n已达到DeepSeek API的速率限制。请稍后再试。"
            else:
                user_friendly_error = f"**API错误**\n\n调用DeepSeek API时发生错误：\n`{str(e)}`"
            yield "persistent_error", 0, user_friendly_error

    # === 文本文件工作流 ===
    if file_ext in text_exts:
        total_steps = 2
        yield "progress", 0 / total_steps, "步骤 1/2: 正在读取文本文档..."
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                full_transcript = f.read()
        except Exception as e:
            user_friendly_error = f"**读取文件失败**\n\n无法读取您上传的文本文档 '{os.path.basename(input_path)}'。\n\n**原始错误信息:**\n`{e}`"
            yield "persistent_error", 0, user_friendly_error
            return
        
        current_progress += 1
        yield "progress", current_progress / total_steps, "步骤 2/2: 正在调用DeepSeek模型生成内容..."
        
        final_path = None
        deepseek_gen = run_deepseek_and_yield_results()
        for event_type, value, *rest in deepseek_gen:
            if event_type == "persistent_error":
                yield event_type, value, rest[0] if rest else ""
                return
            elif event_type == "llm_chunk":
                yield event_type, value
            elif event_type == "save_path":
                final_path = value
                
        if final_path:
            current_progress += 1
            yield "progress", current_progress / total_steps, "处理完成！"
            yield "done", final_path, "🎉 恭喜！智能内容已生成！"
        return

    # === 视频和音频文件工作流 ===
    elif file_ext in video_exts or file_ext in audio_exts:
        is_video = file_ext in video_exts
        total_steps = 4 if is_video else 3
        
        step_name = "视频" if is_video else "音频"
        yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在切分{step_name}为音频块..."
        
        splitter_generator = split_media_to_audio_chunks_generator(input_path, output_dir, 600)
        audio_chunks = []
        
        for event_type, val1, *val2 in splitter_generator:
            if event_type == 'progress':
                completed, total = val1, val2[0]
                yield "sub_progress", completed / total, f"正在切分... ({completed}/{total})"
            elif event_type == 'result':
                audio_chunks = val1
            elif event_type == 'error':
                user_friendly_error = f"**媒体文件切分失败**\n\n无法处理您上传的媒体文件。\n\n**原始错误信息:**\n`{val1}`"
                yield "persistent_error", 0, user_friendly_error
                return
        
        if not audio_chunks:
            yield "persistent_error", 0, f"**{step_name}切分失败**\n\n未能从您的文件中提取出任何音频块。"
            return
        
        yield "sub_progress", 1.0, f"✅ {step_name}切分全部完成！"
        current_progress += 1
        yield "progress", current_progress / total_steps, f"✅ {step_name}切分完成，准备开始转录..."

        yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在并行转录 {len(audio_chunks)} 个音频块..."
        all_transcripts = [None] * len(audio_chunks)
        num_transcribed = 0

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_index = {
                    executor.submit(transcribe_single_audio_chunk, chunk, doubao_app_id, doubao_token): i
                    for i, chunk in enumerate(audio_chunks)
                }
                for future in concurrent.futures.as_completed(future_to_index):
                    index = future_to_index[future]
                    result = future.result() 
                    if result is not None:
                        all_transcripts[index] = result
                    else:
                        raise Exception(f"转录任务未返回有效文本 (块索引: {index})。")
                    
                    num_transcribed += 1
                    yield "sub_progress", num_transcribed / len(audio_chunks), f"正在转录... ({num_transcribed}/{len(audio_chunks)})"

        except Exception as e:
            user_friendly_error = f"**音频转录失败**\n\n在连接语音识别服务进行语音转文字时发生错误。\n\n**原始错误信息:**\n`{e}`"
            yield "persistent_error", 0, user_friendly_error
            return
        
        if any(t is None for t in all_transcripts):
            yield "persistent_error", 0, "**音频转录不完整**\n\n部分音频块在多次尝试后仍然转录失败。"
            return

        yield "sub_progress", 1.0, "✅ 音频转录全部完成！"
        current_progress += 1
        yield "progress", current_progress / total_steps, "所有音频块转录完成！"
        shutil.rmtree(output_dir, ignore_errors=True)

        if is_video:
            yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在汇总文字稿并保存..."
        
        full_transcript = "\n\n".join(filter(None, all_transcripts))
        
        transcript_save_path = "source_transcript.txt"
        try:
            with open(transcript_save_path, 'w', encoding='utf-8') as f:
                f.write(full_transcript)
        except IOError as e:
            yield "error", 0, f"无法保存文字稿文件: {e}"

        if is_video:
            current_progress += 1
            yield "progress", current_progress / total_steps, "文字稿汇总完成。"
            
        yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在调用DeepSeek模型生成内容..."

        final_path = None
        deepseek_gen = run_deepseek_and_yield_results()
        for event_type, value, *rest in deepseek_gen:
            if event_type == "persistent_error":
                yield event_type, value, rest[0] if rest else ""
                return
            elif event_type == "llm_chunk":
                yield event_type, value
            elif event_type == "save_path":
                final_path = value
        
        if final_path:
            current_progress += 1
            yield "progress", current_progress / total_steps, "处理完成！"
            yield "done", final_path, "🎉 恭喜！智能内容已生成！"
        return
        
    else:
        user_friendly_error = f"**不支持的文件类型**\n\n您上传的文件类型 (`{file_ext}`) 当前不受支持。"
        yield "error", 0, user_friendly_error
        return