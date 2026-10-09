"""Render-only visual treatments share one input and one slot output."""
from app.rendering.smart_edit import camera


def slot_graph(normalize,parts,index,incoming,outgoing,fades,smart=None,emphasis=(),*,decorate=True):
    graph=''
    if smart and decorate:
        segments=smart['segments'];labels=''.join(f'[q{j}]' for j in range(len(segments)))
        graph=f'[0:v]{normalize},split={len(segments)}{labels};\n'
        for j,segment in enumerate(segments):
            start=segment['start_frame'];end=segment['end_frame']+(outgoing[index] if j==len(segments)-1 else 0)
            punches=[(round((e['start']-segment['start'])*30),round((e['end']-segment['start'])*30)) for e in emphasis if e.get('punch_in') and e['end']>segment['start'] and e['start']<segment['end']]
            target='treated' if len(segments)==1 else f'seg{j}'
            graph+=f'[q{j}]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS{camera(segment,punches=punches)},format=yuv420p,settb=1/30,setpts=PTS-STARTPTS[{target}];\n'
        if len(segments)>1:graph+=''.join(f'[seg{j}]' for j in range(len(segments)))+f'concat=n={len(segments)}:v=1:a=0,fps=30,settb=1/30,setpts=PTS-STARTPTS[treated];\n'
        source='[treated]'
    else:source=f'[0:v]{normalize},'
    labels=''.join(f'[p{j}]' for j in range(len(parts)))
    graph+=f'{source}split={len(parts)}{labels};\n'
    for j,(name,start,end) in enumerate(parts):
        extra=''
        if name=='core' and decorate:
            if index and fades[index-1]:extra+=f',fade=t=in:st=0:d={min(fades[index-1],(end-start)/90):.6f}'
            if fades[index]:extra+=f',fade=t=out:st={max(0,(end-start)/30-fades[index]):.6f}:d={min(fades[index],(end-start)/90):.6f}'
        graph+=f'[p{j}]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS{extra}[{name}];\n'
    return graph.rstrip(';\n')
