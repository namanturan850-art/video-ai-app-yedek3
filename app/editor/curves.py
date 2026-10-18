"""Shared bounded cubic Bezier evaluation and FFmpeg expressions.

Control coordinates are normalized time/value. Monotone X handles make the
inverse unique. Twenty-four bisections bound time error below 6e-8.
"""

def cubic(t, a, b):
    return 3*(1-t)**2*t*a+3*(1-t)*t*t*b+t**3


def progress(point, u):
    u=max(0.,min(1.,u));kind=point.get('interpolation','linear')
    if kind=='hold':return 0. if u<1 else 1.
    if kind=='ease_in':return u*u
    if kind=='ease_out':return 1-(1-u)**2
    if kind=='ease_in_out':return u*u*(3-2*u)
    if kind!='bezier':return u
    x1,y1,x2,y2=point.get('bezier',[1/3,0.,2/3,1.])
    lo,hi=0.,1.
    for _ in range(24):
        t=(lo+hi)/2
        if cubic(t,x1,x2)<u:lo=t
        else:hi=t
    return cubic((lo+hi)/2,y1,y2)


def progress_expression(point,u):
    kind=point.get('interpolation','linear')
    if kind=='hold':return '0'
    if kind=='ease_in':return f'pow({u},2)'
    if kind=='ease_out':return f'1-pow(1-({u}),2)'
    if kind=='ease_in_out':return f'({u})*({u})*(3-2*({u}))'
    if kind!='bezier':return u
    x1,y1,x2,y2=point.get('bezier',[1/3,0.,2/3,1.])
    # Analytic inversion avoids running a bisection for every opacity pixel.
    # All constants come from validated monotone controls, never user code.
    a=1+3*x1-3*x2;b=3*x2-6*x1;c=3*x1
    if abs(a)<1e-10:
        if abs(b)<1e-10:inverse=f'({u})/{c}'
        else:inverse=f'(-{c}+sqrt(max(0,{c*c}+{4*b}*({u}))))/{2*b}'
        prefix=f'st(3,clip({inverse},0,1));'
    else:
        p=(3*a*c-b*b)/(3*a*a);q0=(2*b*b*b-9*a*b*c)/(27*a*a*a);shift=b/(3*a)
        def root(v):return f'(sgn({v})*pow(abs({v}),1/3))'
        cardano=f'{root("(-ld(1)/2+sqrt(max(0,ld(2))))")}+{root("(-ld(1)/2-sqrt(max(0,ld(2))))")}-{shift}'
        if p<0:
            import math
            r=2*math.sqrt(-p/3);factor=3/(2*p)*math.sqrt(-3/p)
            roots=[f'({r}*cos(acos(clip(ld(1)*{factor},-1,1))/3-{2*math.pi*k/3})-{shift})' for k in range(3)]
            trig=f'st(3,{roots[0]});if(between(ld(3),-0.000001,1.000001),ld(3),st(3,{roots[1]});if(between(ld(3),-0.000001,1.000001),ld(3),{roots[2]}))'
        else:trig=cardano
        prefix=f'st(1,{q0}-({u})/{a});st(2,ld(1)*ld(1)/4+{(p/3)**3});st(3,clip(if(gte(ld(2),0),{cardano},{trig}),0,1));'
    return prefix+f'(3*pow(1-ld(3),2)*ld(3)*{y1}+3*(1-ld(3))*pow(ld(3),2)*{y2}+pow(ld(3),3))'
