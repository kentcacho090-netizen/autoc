"""Android screenshot observation using native Termux OCR."""
from dataclasses import dataclass, field, asdict
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

try:
    from PIL import Image
except ImportError:
    Image = None

@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    game_viewport: str = "unknown"
    resources: Dict[str, Optional[int]] = field(default_factory=lambda: {"gold":None,"elixir":None,"dark_elixir":None,"builder_gold":None,"builder_elixir":None,"gems":None})
    text: str = ""
    confidence: float = 0.0
    source: str = "none"
    regions_read: int = 0
    diagnostics: str = ""
    def to_dict(self): return asdict(self)

class ScreenDetector:
    """Safe CoC OCR for Termux; avoids PIL native image filters."""
    def __init__(self, controller, config_path="detector_config.json"):
        self.controller=controller; self.config=self._load_config(config_path); self.regions=self.config.get("regions",{})
        ocr=self.config.get("ocr",{}); self.scale=max(2,int(ocr.get("scale",3))); self.threshold=int(ocr.get("threshold",165))
    @staticmethod
    def _load_config(path):
        try:
            with open(path,"r",encoding="utf-8") as f: return json.load(f)
        except (OSError,json.JSONDecodeError): return {}
    def capture(self,filename="autoc_observation.png"): return self.controller.take_screenshot(filename)
    @staticmethod
    def parse_number(text):
        if not text: return None
        raw=text.strip().upper().replace(" ","")
        if not re.fullmatch(r"[0-9][0-9,\.]*[KMB]?",raw): return None
        suffix=raw[-1:] if raw[-1:] in "KMB" else ""; token=raw[:-1] if suffix else raw
        if suffix:
            try: return int(float(token.replace(",",""))*{"K":10**3,"M":10**6,"B":10**9}[suffix])
            except ValueError: return None
        try: return int(token.replace(",","").replace(".",""))
        except ValueError: return None
    @staticmethod
    def _find_game_viewport(image): return image,(0,0,image.width,image.height),"none"
    @staticmethod
    def _crop_norm(image,region):
        x,y,w,h=[float(v) for v in region]
        return image.crop((max(0,int(x*image.width)),max(0,int(y*image.height)),min(image.width,int((x+w)*image.width)),min(image.height,int((y+h)*image.height))))
    def _white_text_mask(self,crop):
        rgb=crop.convert("RGB"); width,height=rgb.size; out=Image.new("L",(width,height),0); src=list(rgb.getdata()); dst=[0]*(width*height)
        for i,(r,g,b) in enumerate(src):
            hi,lo=max(r,g,b),min(r,g,b)
            if hi>=self.threshold and hi-lo<=65 and r+g+b>=520: dst[i]=255
        out.putdata(dst); return out
    def _tesseract(self,image):
        if Image is None or not shutil.which("tesseract"): return ""
        temp=None
        try:
            fd,temp=tempfile.mkstemp(suffix=".png"); os.close(fd); image.save(temp,format="PNG")
            result=subprocess.run(["tesseract",temp,"stdout","--psm","7","-c","tessedit_char_whitelist=0123456789KMB","-c","load_system_dawg=0","-c","load_freq_dawg=0"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=8)
            return result.stdout.strip()
        except (OSError,subprocess.SubprocessError): return ""
        finally:
            if temp:
                try: os.unlink(temp)
                except OSError: pass
    def _resource_number(self,image,region)->Tuple[Optional[int],str,float]:
        crop=self._crop_norm(image,region); mask=self._white_text_mask(crop); bbox=mask.getbbox()
        if not bbox: return None,"",0.0
        bw,bh=bbox[2]-bbox[0],bbox[3]-bbox[1]
        if bw<10 or bh<6: return None,"",0.0
        px,py=max(4,int(bw*.10)),max(4,int(bh*.35)); x1,y1=max(0,bbox[0]-px),max(0,bbox[1]-py); x2,y2=min(mask.width,bbox[2]+px),min(mask.height,bbox[3]+py)
        digit=mask.crop((x1,y1,x2,y2)).resize(((x2-x1)*self.scale,(y2-y1)*self.scale)); raw=self._tesseract(digit); value=self.parse_number(raw)
        return (value,raw,.85) if value is not None and 0<=value<=2_000_000_000 else (None,"",0.0)
    @staticmethod
    def _default_hud_regions():
        return {"gold":[0.800,0.015,0.185,0.075],"elixir":[0.800,0.105,0.185,0.075],"dark_elixir":[0.800,0.195,0.185,0.075],"gems":[0.800,0.285,0.185,0.075]}
    def observe(self,image_path=None):
        path=image_path or self.capture()
        if not path or not os.path.exists(path): return Observation(source="screenshot_failed")
        if not shutil.which("tesseract"): return Observation(source="tesseract_missing")
        if Image is None: return Observation(source="pillow_missing")
        try:
            with Image.open(path) as original:
                original=original.convert("RGB"); width,height=original.size; game,bounds,rotation=self._find_game_viewport(original); regions=self._default_hud_regions(); configured=self.regions if isinstance(self.regions,dict) else {}
                for key in regions:
                    candidate=configured.get(key)
                    if isinstance(candidate,(list,tuple)) and len(candidate)==4: regions[key]=list(candidate)
                resources={"gold":None,"elixir":None,"dark_elixir":None,"builder_gold":None,"builder_elixir":None,"gems":None}; raw_parts=[]; confs=[]
                for key in ("gold","elixir","dark_elixir","gems"):
                    value,raw,conf=self._resource_number(game,regions[key]); resources[key]=value
                    if raw: raw_parts.append(f"{key}:{raw}"); confs.append(conf)
                village="home" if resources["gold"] is not None and resources["elixir"] is not None else "unknown"; confidence=sum(confs)/len(confs) if confs else 0.0
                diagnostics=f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; rotation={rotation}; resource_regions=wide-right; raw="+" || ".join(raw_parts)
                return Observation(village=village,orientation="landscape" if width>height else "portrait",screen_size=f"{width}x{height}",game_viewport=f"{game.width}x{game.height}",resources=resources,text=" || ".join(raw_parts),confidence=confidence,source="tesseract-white-mask-safe",regions_read=len(raw_parts),diagnostics=diagnostics)
        except Exception as exc: return Observation(source="image_error",diagnostics=str(exc))
