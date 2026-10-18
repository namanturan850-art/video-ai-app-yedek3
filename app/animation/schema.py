"""Versioned, bounded JSON components. Coordinates use a 1920×1080 canvas."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Color=Annotated[str,Field(pattern=r'^#[0-9a-fA-F]{6}$')]


def validation_text(error):
    messages=[]
    for e in error.errors(include_input=False,include_url=False)[:5]:
        kind=e['type'];context=e.get('ctx',{})
        if kind=='literal_error':message='Desteklenen değerlerden biri gerekir: '+context.get('expected','paketteki seçenekler')
        elif kind=='extra_forbidden':message='Desteklenmeyen alan; paketteki animasyon şemasını kullanın.'
        elif kind=='missing':message='Bu alan gereklidir.'
        elif kind=='value_error':message=e['msg'].removeprefix('Value error, ')
        elif kind in ('float_type','int_type','finite_number'):message='Sonlu bir sayı gereklidir.'
        elif kind in ('greater_than','greater_than_equal','less_than','less_than_equal'):message='Sayı izin verilen sınırların dışında: '+str(context)
        elif kind in ('too_long','too_short','string_too_long','string_too_short'):message='Liste/yazı uzunluğu desteklenen sınırların dışında.'
        elif kind in ('string_type','string_pattern_mismatch'):message='Metin/kimlik/renk biçimini kontrol edin.'
        else:message='Alan türü veya değeri geçersiz; paketteki şemayı kullanın.'
        messages.append('.'.join(map(str,e['loc']))+': '+message)
    return '; '.join(messages)


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)


class Point(Strict):
    x: float=Field(ge=-1920,le=1920)
    y: float=Field(ge=-1080,le=1080)


class Key(Strict):
    time: float=Field(ge=0,le=30)
    property: Literal['x','y','scale','rotation','opacity','progress']
    value: float
    easing: Literal['linear','ease_in_out','hold']='ease_in_out'

    @model_validator(mode='after')
    def bounds(self):
        low,high={'x':(-1920,3840),'y':(-1080,2160),'scale':(.1,4),'rotation':(-360,360),'opacity':(0,1),'progress':(0,1)}[self.property]
        if not low<=self.value<=high:raise ValueError(f'{self.property} değeri {low}–{high} aralığında olmalıdır.')
        return self


class Cloud(Strict):
    lobes: int=Field(default=5,ge=3,le=7)
    drift: float=Field(default=12,ge=-120,le=120)


class Path(Strict):
    points: list[Point]=Field(min_length=2,max_length=32)
    speed: float=Field(default=80,ge=0,le=300)
    particles: int=Field(default=4,ge=0,le=16)


class Lightning(Strict):
    segments: int=Field(default=9,ge=3,le=24)
    seed: int=Field(default=1,ge=0,le=9999)
    frequency: float=Field(default=1,ge=.2,le=2)


class BarsItem(Strict):
    label: str=Field(min_length=1,max_length=45,pattern=r'^[^\x00-\x1f\x7f]+$')
    value: float=Field(ge=0,le=1e12)


class Bars(Strict):
    items: list[BarsItem]=Field(min_length=2,max_length=8)
    unit: str=Field(default='',max_length=20,pattern=r'^[^\x00-\x1f\x7f]*$')


class Text(Strict):
    text: str=Field(min_length=1,max_length=100,pattern=r'^[^\x00-\x1f\x7f]+$')
    font_size: int=Field(default=44,ge=18,le=96)


class Counter(Strict):
    value: float=Field(ge=0,le=1e12)
    unit: str=Field(default='',max_length=20,pattern=r'^[^\x00-\x1f\x7f]*$')
    font_size: int=Field(default=64,ge=18,le=96)


class Wave(Strict):
    amplitude: float=Field(default=24,ge=0,le=120)
    cycles: float=Field(default=2,ge=.1,le=8)
    frequency: float=Field(default=.5,ge=0,le=2)


class Particles(Strict):
    count: int=Field(default=24,ge=1,le=64)
    seed: int=Field(default=1,ge=0,le=9999)
    speed: float=Field(default=40,ge=0,le=200)
    direction: float=Field(default=90,ge=-180,le=180)


class Empty(Strict):pass

DATA={'cloud':Cloud,'flow':Path,'arrow':Path,'line':Path,'lightning':Lightning,'bar_chart':Bars,
      'line_chart':Bars,'label':Text,'node':Text,'counter':Counter,'wave':Wave,'particles':Particles,
      'box':Empty,'circle':Empty,'isometric_box':Empty}


class Actor(Strict):
    id: str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    kind: Literal['cloud','flow','arrow','line','lightning','bar_chart','line_chart','label','node','counter','wave','particles','box','circle','isometric_box']
    layer: int=Field(default=0,ge=0,le=100)
    x: float=Field(default=960,ge=-1920,le=3840)
    y: float=Field(default=540,ge=-1080,le=2160)
    width: float=Field(default=320,ge=8,le=1800)
    height: float=Field(default=180,ge=8,le=950)
    color: Color='#7DC8FF'
    stroke: Color='#E8F0FF'
    line_width: int=Field(default=4,ge=1,le=20)
    scale: float=Field(default=1,ge=.1,le=4)
    rotation: float=Field(default=0,ge=-360,le=360)
    opacity: float=Field(default=1,ge=0,le=1)
    progress: float=Field(default=1,ge=0,le=1)
    start: float=Field(default=0,ge=0,le=30)
    end: float|None=Field(default=None,gt=0,le=30)
    keyframes: list[Key]=Field(default_factory=list,max_length=64)
    data: dict=Field(default_factory=dict)

    @model_validator(mode='after')
    def valid(self):
        if len({(k.property,k.time) for k in self.keyframes})!=len(self.keyframes):raise ValueError('Yinelenen nesne keyframe zamanı.')
        if self.end is not None and self.end<=self.start:raise ValueError('Nesne bitişi başlangıçtan sonra olmalıdır.')
        try:self.data=DATA[self.kind].model_validate(self.data).model_dump()
        except ValidationError as error:raise ValueError(f'{self.id}/{self.kind}: '+validation_text(error)) from None
        return self


class Camera(Strict):
    x: float=Field(default=0,ge=-1920,le=1920)
    y: float=Field(default=0,ge=-1080,le=1080)
    scale: float=Field(default=1,ge=.5,le=2)
    keyframes: list[Key]=Field(default_factory=list,max_length=32)

    @model_validator(mode='after')
    def valid(self):
        if any(k.property not in ('x','y','scale') or k.property=='scale' and not .5<=k.value<=2 or k.property=='x' and abs(k.value)>1920 or k.property=='y' and abs(k.value)>1080 for k in self.keyframes):
            raise ValueError('Kamera yalnız X/Y ve 0.5–2 ölçek destekler.')
        if len({(k.property,k.time) for k in self.keyframes})!=len(self.keyframes):raise ValueError('Yinelenen kamera keyframe zamanı.')
        return self


class Animation(Strict):
    version: Literal['naman.animation.v1']=Field(alias='schema')
    basis: Literal['schematic','narration','demo']
    background: Color|None=None
    camera: Camera=Field(default_factory=Camera)
    objects: list[Actor]=Field(min_length=1,max_length=32)

    @model_validator(mode='after')
    def unique(self):
        if len({a.id for a in self.objects})!=len(self.objects):raise ValueError('Yinelenen animasyon nesne kimliği.')
        if sum(a.data.get('count',a.data.get('particles',0)) for a in self.objects)>256:raise ValueError('Sahnede en fazla 256 parçacık desteklenir.')
        return self


def validate(data,narration,duration=None):
    """Facts come only from actual narration; demo data has an immutable notice."""
    model=Animation.model_validate(data)
    from app.motion.templates import in_narration
    from app.motion.numbers import is_spoken
    for actor in model.objects:
        d=actor.data
        if any(isinstance(t,str) and not t.strip() for t in [d.get('text'),*[r['label'] for r in d.get('items',[])]]):
            raise ValueError(f'{actor.id}: yazı/etiket boş bırakılamaz.')
        if model.basis!='demo':
            for text in [d.get('text'),d.get('unit'),*[r['label'] for r in d.get('items',[])]]:
                if text and not in_narration(text,narration):raise ValueError(f'{actor.id}: metin/birim sahne anlatımında geçmelidir: {text}')
            values=[r['value'] for r in d.get('items',[])]+([d['value']] if 'value' in d else [])
            if values and model.basis!='narration':raise ValueError(f'{actor.id}: sayısal grafik narration veya açık demo temeli gerektirir.')
            for value in values:
                if not is_spoken(format(value,'.12g'),narration):raise ValueError(f'{actor.id}: {value:g} sayısı anlatımdan doğrulanamadı.')
        if duration is not None:
            end=actor.end if actor.end is not None else duration
            if not 1/30<=duration<=30 or not actor.start<end<=duration+1e-6 or any(k.time>duration+1e-6 for k in actor.keyframes):
                raise ValueError(f'{actor.id}: nesne/keyframe zamanı 0–{duration:.3f} sn içinde olmalıdır; sahne en fazla 30 sn olabilir.')
    if duration is not None and any(k.time>duration+1e-6 for k in model.camera.keyframes):raise ValueError('Kamera keyframe zamanı animasyonu aşıyor.')
    return model.model_dump(by_alias=True)
