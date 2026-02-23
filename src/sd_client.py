import requests
import io
import base64
from PIL import Image
from datetime import datetime
from pathlib import Path
from typing import Optional


class SDClient:
    """Stable Diffusion客户端，用于生成插图"""
    
    def __init__(
        self,
        url: str = "http://127.0.0.1:7860",
        output_dir: str = "output",
        width: int = 512,
        height: int = 768,
        steps: int = 25,
        cfg_scale: float = 7,
        sampler_name: str = "DPM++ 2M Karras"
    ):
        """
        初始化SD客户端
        
        Args:
            url: SD WebUI API地址
            output_dir: 输出目录
            width: 图片宽度
            height: 图片高度
            steps: 生成步数
            cfg_scale: 提示词相关性
            sampler_name: 采样器名称
        """
        self.url = url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.width = width
        self.height = height
        self.steps = steps
        self.cfg_scale = cfg_scale
        self.sampler_name = sampler_name
    
    def generate_illustration(
        self,
        prompt: str,
        negative_prompt: str = "",
        output_filename: Optional[str] = None,
        output_dir: Optional[str] = None,
        seed: int = -1
    ) -> Optional[str]:
        """
        调用本地 SD WebUI 生成图片
        
        Args:
            prompt: 正面提示词
            negative_prompt: 负面提示词
            output_filename: 输出文件名（不含路径），None则自动生成
            output_dir: 输出目录，None则使用初始化时的output_dir
            seed: 随机种子，-1表示随机
        
        Returns:
            保存的图片文件路径，失败返回None
        """
        # 构造请求体 (Payload)
        # 这些参数是专门针对 Counterfeit-V3.0 优化的
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,

            # 核心参数
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "width": self.width,
            "height": self.height,

            # 采样器 (Counterfeit 推荐 DPM++ 2M Karras)
            "sampler_name": self.sampler_name,

            # 种子 (-1 代表随机)
            "seed": seed,

            # 面部修复 (二次元模型通常建议关闭，否则脸会变三次元)
            "restore_faces": False,
        }

        print(f"正在请求绘图 API... Prompt: {prompt[:50]}...")

        try:
            # 发送 POST 请求到 /sdapi/v1/txt2img
            response = requests.post(f"{self.url}/sdapi/v1/txt2img", json=payload)

            if response.status_code == 200:
                r = response.json()

                # 获取 Base64 编码的图片数据
                # WebUI 返回的是一个列表，通常我们只取第一张
                image_b64 = r['images'][0]

                # 解码并保存图片
                image = Image.open(io.BytesIO(base64.b64decode(image_b64)))

                # 确定输出目录
                if output_dir:
                    output_path = Path(output_dir)
                    output_path.mkdir(parents=True, exist_ok=True)
                else:
                    output_path = self.output_dir

                # 生成文件名
                if output_filename:
                    file_path = output_path / output_filename
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                    file_path = output_path / f"illustration_{timestamp}.png"
                
                image.save(file_path)

                print(f"✅ 图片已保存至: {file_path}")
                return str(file_path)
            else:
                print(f"❌ 请求失败，状态码: {response.status_code}")
                print(response.text)
                return None

        except Exception as e:
            print(f"❌ 连接错误: {e}")
            return None


# 为了向后兼容，保留原有函数
def generate_illustration(prompt, negative_prompt="", output_dir="output"):
    """
    调用本地 SD WebUI 生成图片（兼容旧版本）
    
    Args:
        prompt: 正面提示词
        negative_prompt: 负面提示词
        output_dir: 输出目录
    """
    client = SDClient(output_dir=output_dir)
    return client.generate_illustration(prompt, negative_prompt)


# --- 测试代码 ---
if __name__ == "__main__":
    # 这里是 Counterfeit-V3.0 的起手式，务必保留
    base_positive = "(masterpiece, best quality), "
    # 这里是 Counterfeit-V3.0 的核心负面词，务必保留 EasyNegative
    base_negative = "EasyNegative, (worst quality, low quality:1.4), lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry"

    # 测试生成一个 "在废墟中读书的女孩"
    test_prompt = base_positive + "1girl, sitting, reading book, ruins, cloudy sky, wind, white dress"

    client = SDClient(output_dir="output")
    client.generate_illustration(test_prompt, base_negative)