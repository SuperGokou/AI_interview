"""Download the official MuseTalk inference weights; resumable via curl."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
files = [
 ('TMElyralab/MuseTalk','musetalkV15/musetalk.json','musetalkV15/musetalk.json'),
 ('TMElyralab/MuseTalk','musetalkV15/unet.pth','musetalkV15/unet.pth'),
 ('stabilityai/sd-vae-ft-mse','config.json','sd-vae/config.json'),
 ('stabilityai/sd-vae-ft-mse','diffusion_pytorch_model.bin','sd-vae/diffusion_pytorch_model.bin'),
 ('openai/whisper-tiny','config.json','whisper/config.json'),
 ('openai/whisper-tiny','pytorch_model.bin','whisper/pytorch_model.bin'),
 ('openai/whisper-tiny','preprocessor_config.json','whisper/preprocessor_config.json'),
]
def fetch(item):
 repo, source, dest = item
 path = Path('models') / dest
 path.parent.mkdir(parents=True, exist_ok=True)
 for host in ['https://hf-mirror.com','https://huggingface.co']:
  result = subprocess.run(['curl','-fL','--retry','2','--connect-timeout','15','--max-time','1800','--speed-limit','1024','--speed-time','45','-C','-','-o',str(path),f'{host}/{repo}/resolve/main/{source}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  if result.returncode == 0:
   print(f'OK {dest} {path.stat().st_size}',flush=True)
   return
 raise RuntimeError(f'Download failed: {dest}')
with ThreadPoolExecutor(max_workers=4) as pool:
 list(pool.map(fetch, files))
