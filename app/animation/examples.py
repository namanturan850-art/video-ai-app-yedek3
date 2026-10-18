"""Explicitly labelled synthetic demonstrations, not verified scientific datasets."""
from copy import deepcopy


def examples(duration=1.):
    base={'schema':'naman.animation.v1','basis':'demo','background':None,'objects':[]}
    science=deepcopy(base)
    science['objects']=[
        {'id':'cloud-left','kind':'cloud','x':620.,'y':310.,'width':440.,'height':180.,'layer':1,'color':'#657992','data':{'drift':18.}},
        {'id':'cloud-right','kind':'cloud','x':1150.,'y':280.,'width':500.,'height':210.,'layer':1,'color':'#93AAC7','data':{'drift':-12.}},
        {'id':'air','kind':'flow','x':900.,'y':500.,'layer':2,'color':'#77DDE7','data':{'speed':160.,'points':[{'x':-500.,'y':80.},{'x':-100.,'y':-20.},{'x':400.,'y':-70.}] }},
        {'id':'bolt','kind':'lightning','x':1000.,'y':560.,'width':100.,'height':380.,'layer':3,'color':'#B8D9FF','stroke':'#FFFFFF','data':{'seed':13}},
        {'id':'rain','kind':'particles','x':950.,'y':700.,'width':700.,'height':260.,'opacity':.5,'data':{'seed':11,'direction':100.,'speed':110.}}]
    chart=deepcopy(base)
    chart['objects']=[{'id':'data','kind':'bar_chart','x':960.,'y':490.,'width':1040.,'height':420.,'color':'#6BD7B6',
                       'data':{'items':[{'label':'A','value':20.},{'label':'B','value':40.},{'label':'C','value':60.}],'unit':'DEMO'}},
                      {'id':'title','kind':'label','x':960.,'y':150.,'width':1400.,'data':{'text':'Hareketli veri grafiği'}}]
    diagram=deepcopy(base)
    diagram['camera']={'keyframes':[{'property':'scale','time':0.,'value':1.},{'property':'scale','time':duration,'value':1.05}]}
    diagram['objects']=[{'id':'input','kind':'node','x':430.,'y':500.,'width':360.,'height':170.,'layer':2,'color':'#204B6E','data':{'text':'Girdi'}},
                        {'id':'output','kind':'node','x':1470.,'y':500.,'width':360.,'height':170.,'layer':2,'color':'#214E43','data':{'text':'Sonuç'}},
                        {'id':'link','kind':'flow','x':960.,'y':500.,'data':{'points':[{'x':-340.,'y':0.},{'x':340.,'y':0.}],'speed':200.}},
                        {'id':'module','kind':'isometric_box','x':960.,'y':740.,'width':170.,'height':90.,'layer':1,'opacity':.8}]
    return {'science':science,'chart':chart,'diagram':diagram}
