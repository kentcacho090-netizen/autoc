"""Android screenshot observation using native Termux OCR."""
from dataclasses import dataclass, field, asdict
import json, os, re, shutil, subprocess, tempfile
from typing import Dict, Optional
try:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
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
    def __init__(self, controller, config_path="detector_config.json"):
        self.controller=controller; self.config=self._load_config(config_path); self.regions=self.config.get("regions",{}); ocr=self.config.get("ocr",{}); self.psm=int(ocr.get("psm",7)); self.scale=max(1,int(ocr.get("scale",4)))
    @staticmethod
    def _load_config(path):
        try:
            with open(path,"r",encoding="utf-8") as f:return json.load(f)
        except (OSError,json.JSONDecodeError):return {}
    def capture(self,filename="autoc_observation.png"):return self.controller.take_screenshot(filename)
    @staticmethod
    def parse_number(text):
        if not text:return None
        cleaned=text.upper().replace("O","0").replace("I","1").replace("L","1").replace("S","5").replace("B","8")
        m=re.search(r"\d[\d,\.]*\s*[KMB]?",cleaned)
        if not m:return None
        token=m.group(0).replace(",","").replace(" ",""); suffix=token[-1:]; mult={"K":1000,"M":1000000,"B":1000000000}.get(suffix,1)
        if suffix in "KMB":token=token[:-1]
        try:return int(float(token)*mult)
        except ValueError:return None
    @staticmethod
    def _find_game_viewport(image):
        w,h=image.size; rgb=image.convert("RGB"); sw=min(256,w); sh=min(256,h); small=rgb.resize((sw,sh)); px=small.load()
        rows=[sum(1 for x in range(sw) if max(px[x,y])-min(px[x,y])>=25 and sum(px[x,y])>=75)/sw for y in range(sh)]
        cols=[sum(1 for y in range(sh) if max(px[x,y])-min(px[x,y])>=25 and sum(px[x,y])>=75)/sh for x in range(sw)]
        def seg(v,t=.20):
            best=(0,len(v)-1); start=None
            for i,val in enumerate(v+[0.0]):
                if val>=t and start is None:start=i
                elif val<t and start is not None:
                    c=(start,i-1)
                    if c[1]-c[0]>best[1]-best[0]:best=c
                    start=None
            return best
        ys,xs=seg(rows),seg(cols); x1=int(xs[0]*w/sw); x2=int((xs[1]+1)*w/sw); y1=int(ys[0]*h/sh); y2=int((ys[1]+1)*h/sh)
        if x2-x1<w*.45 or y2-y1<h*.35:return image,(0,0,w,h),"full-screen-fallback"
        vp=image.crop((x1,y1,x2,y2))
        if vp.height>vp.width:return vp.rotate(90,expand=True),(x1,y1,x2,y2),"ccw"
        return vp,(x1,y1,x2,y2),"none"
    def _read_region(self,image,region=None):
        if not shutil.which("tesseract") or Image is None:return ""
        temp=None
        try:
            if region:
                x,y,w,h=[float(v) for v in region]; crop=image.crop((max(0,int(x*image.width)),max(0,int(y*image.height)),min(image.width,int((x+w)*image.width)),min(image.height,int((y+h)*image.height))))
            else:crop=image
            gray=ImageOps.grayscale(crop); gray=ImageEnhance.Contrast(gray).enhance(3.5); gray=gray.filter(ImageFilter.SHARPEN); gray=gray.resize((gray.width*self.scale,gray.height*self.scale)); threshold=int(self.config.get("ocr",{}).get("threshold",145)); gray=gray.point(lambda p:255 if p>=threshold else 0)
            fd,temp=tempfile.mkstemp(suffix=".png"); os.close(fd); gray.save(temp); out=[]
            for psm in (7,6,11,13):
                r=subprocess.run(["tesseract",temp,"stdout","--psm",str(psm),"-c","tessedit_char_whitelist=0123456789KMBkmb,."],capture_output=True,text=True,timeout=15)
                if r.stdout.strip():out.append(r.stdout.strip())
            return " | ".join(dict.fromkeys(out))
        except (OSError,subprocess.SubprocessError):return ""
        finally:
            if temp:
                try:os.unlink(temp)
                except OSError:pass
    @staticmethod
    def _default_hud_regions():
        return {"gold":[.84,.025,.155,.070],"elixir":[.84,.095,.155,.070],"dark_elixir":[.84,.165,.155,.070],"gems":[.84,.235,.155,.070],"builders":[.43,.025,.22,.075]}
    def _best(self,raw):
        vals=[self.parse_number(p) for p in (raw or "").split("|")]; vals=[v for v in vals if v is not None]; return max(vals) if vals else None
    def observe(self,image_path=None):
        path=image_path or self.capture()
        if not path or not os.path.exists(path):return Observation(source="screenshot_failed")
        if not shutil.which("tesseract"):return Observation(source="tesseract_missing")
        if Image is None:return Observation(source="pillow_missing")
        try:
            with Image.open(path) as original:
                original=original.convert("RGB"); width,height=original.size; screen_orientation="landscape" if width>height else "portrait" if height>width else "square"; game,bounds,rotation=self._find_game_viewport(original); regions=self._default_hud_regions(); regions.update({k:v for k,v in self.regions.items() if isinstance(v,(list,tuple)) and len(v)==4}); texts={k:self._read_region(game,v) for k,v in regions.items()}
                resources={"gold":self._best(texts.get("gold")),"elixir":self._best(texts.get("elixir")),"dark_elixir":self._best(texts.get("dark_elixir")),"builder_gold":self._best(texts.get("builder_gold")),"builder_elixir":self._best(texts.get("builder_elixir")),"gems":self._best(texts.get("gems"))}; home=sum(resources[k] is not None for k in ("gold","elixir","dark_elixir")); bb=sum(resources[k] is not None for k in ("builder_gold","builder_elixir")); village="builder_base" if bb>home else "home" if home else "unknown"; expected=("gold","elixir","dark_elixir","gems"); confidence=sum(resources[k] is not None for k in expected)/len(expected); diagnostics=f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; rotation={rotation}; hud="+" || ".join(f"{k}:{v[:160]}" for k,v in texts.items() if v)
                return Observation(village=village,orientation="landscape" if game.width>game.height else screen_orientation,screen_size=f"{width}x{height}",game_viewport=f"{game.width}x{game.height}",resources=resources,text=" ".join(v for v in texts.values() if v),confidence=confidence,source="tesseract",regions_read=sum(bool(v) for v in texts.values()),diagnostics=diagnostics)
        except Exception as exc:return Observation(source="image_error",diagnostics=str(exc))
