"""Render-only deterministic source windows. No file/provider mutation or speed-up."""
import hashlib


def source_window(duration,used,identity,seed=''):
    duration=float(duration or used);used=float(used)
    spare=max(0,duration-used-.6)  # Retain room for native transition handles.
    margin=min(.35,spare/4)
    fraction=int(hashlib.sha256(f'{identity}:{seed}'.encode()).hexdigest()[:8],16)/0xffffffff
    start=margin+(spare-2*margin)*(.25+.5*fraction) if spare else 0.
    start=round(start,6)
    return {'source_duration':duration,'source_in':start,'source_out':round(min(duration,start+used),6),
            'source_trim_start':start,'source_trim_end':round(min(duration,start+used),6),'used_duration':used}
