TEAL=('#e7f1ed','#1f6a5a'); AMBER=('#f8efe1','#b36a12'); GRAY=('#f3f5f4','#8aa09a'); RED=('#fbeaea','#a83535'); WHITE=('#ffffff','#1d2a2f')
def svg(w,h,body,mid):
    return (f'<figure><svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<defs><marker id="m{mid}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
            f'<path d="M2 1L8 5L2 9" fill="none" stroke="#5b6b70" stroke-width="1.6"/></marker></defs>'
            f'<g font-size="12" text-anchor="middle">{body}</g></svg>')
def box(x,y,w,h,t,sub=None,c=GRAY,sw=1,dash=False):
    d=' stroke-dasharray="4 3"' if dash else ''
    s=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{c[0]}" stroke="{c[1]}" stroke-width="{sw}"{d}/>'
    if sub:
        s+=f'<text x="{x+w/2}" y="{y+h/2-2}" fill="#1d2a2f">{t}</text><text x="{x+w/2}" y="{y+h/2+13}" font-size="10" fill="#5b6b70">{sub}</text>'
    else:
        s+=f'<text x="{x+w/2}" y="{y+h/2+4}" fill="#1d2a2f">{t}</text>'
    return s
def arrow(x1,y1,x2,y2,mid,color='#5b6b70',dash=False,w=1.3):
    d=' stroke-dasharray="4 3"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"{d} marker-end="url(#m{mid})"/>'
def path(d,mid,color='#5b6b70',dash=False):
    ds=' stroke-dasharray="4 3"' if dash else ''
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.3"{ds} marker-end="url(#m{mid})"/>'
def line(x1,y1,x2,y2,color='#8aa09a',w=1,dash=False):
    d=' stroke-dasharray="4 3"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"{d}/>'
def text(x,y,t,size=10.5,color='#5b6b70',anchor='middle'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{t}</text>'
def cap(n,t): return f'<figcaption>Figure {n} {t}</figcaption></figure>'
