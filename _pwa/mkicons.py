# Polaris 앱 아이콘 생성 (허브 북극성 SVG 모티프). 사용: python3 _pwa/mkicons.py icons  (Pillow 필요)
import sys
from PIL import Image, ImageDraw, ImageFilter
OUT = sys.argv[1]
BG = (11, 13, 20)
STAR = [(12,1.5),(13.4,9.2),(21,10.6),(13.8,12),(12,22.5),(10.2,12),(3,10.6),(10.6,9.2)]
def lerp(a,b,t): return tuple(int(a[i]+(b[i]-a[i])*t) for i in range(3))
def icon(size, scale):
    S = size*4
    img = Image.new('RGB',(S,S),BG)
    # soft radial glow
    glow = Image.new('L',(S,S),0); gd = ImageDraw.Draw(glow)
    r = S*0.36*scale/0.62
    gd.ellipse([S/2-r,S/2-r,S/2+r,S/2+r], fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(S*0.12))
    img.paste(Image.new('RGB',(S,S),(139,155,255)),(0,0),glow)
    # gradient star (#dfe4ff -> #8b9bff, top-left to bottom-right)
    grad = Image.new('RGB',(S,S))
    gp = grad.load()
    c0, c1 = (223,228,255), (139,155,255)
    for y in range(0,S,4):
        for x in range(0,S,4):
            col = lerp(c0,c1,min(1,max(0,(x+y)/(2*S))))
            for dy in range(4):
                for dx in range(4):
                    gp[x+dx,y+dy] = col
    mask = Image.new('L',(S,S),0)
    k = S*scale/24; off = S*(1-scale)/2
    ImageDraw.Draw(mask).polygon([(off+x*k, off+y*k) for x,y in STAR], fill=255)
    img.paste(grad,(0,0),mask)
    return img.resize((size,size), Image.LANCZOS)
icon(192,0.62).save(f'{OUT}/icon-192.png')
icon(512,0.62).save(f'{OUT}/icon-512.png')
icon(512,0.46).save(f'{OUT}/icon-maskable-512.png')
icon(180,0.62).save(f'{OUT}/apple-touch-icon.png')
icon(32,0.8).save(f'{OUT}/favicon-32.png')
