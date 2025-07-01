## 🚀 如何运行

### 1. 前提条件

- **Python 3.8+**
- **FFmpeg**: 这是视频和音频处理所必需的。 请确保您已在系统中安装了 FFmpeg，并且其路径已添加到系统环境变量中。

#### ffmpeg安装教程

访问官方下载界面 https://ffmpeg.org/download.html

根据您的系统架构下载文件。如果下载的是压缩包，将解压后文件放在一个您喜欢的位置

之后需要配置系统的环境变量：

### 2. 安装与配置

1.  **克隆或下载项目**
    将所有项目文件保存在本地文件夹中。

2.  **创建并激活虚拟环境** (推荐)
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS / Linux
    source venv/bin/activate
    ```
    也可以使用anaconda创建虚拟环境
    ```bash
    conda create -n venv python=3.11
    conda activate venv
    ```

3.  **安装所有依赖**
    在终端中运行以下命令，安装所有需要的库：
    ```bash
    pip install -r requirements.txt
    ```

### 3. 启动Web应用

在您的命令行终端中，运行以下命令：

```bash
streamlit run app.py
```

### 4.Web应用的使用


生成笔记选择"Notes"，可以传入回放文件/课程录音稿/录音转写稿

"Q&A" 准备做成deepseek的网页版问答，还未实现，目前需要传.txt，文件内容是你想问的问题

"Quiz"传入文档，可以根据课程录音转文字稿/课程笔记生成测试题
